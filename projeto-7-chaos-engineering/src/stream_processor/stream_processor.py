"""
Projeto 7 — Stream Processor: Atualizador de Contadores Materializados
======================================================================

Processa eventos do DynamoDB Stream da tabela de transações e mantém
contadores incrementais por região na tabela transaction_counters.

Evita Scan O(N) na tabela principal — leitura de contador é O(1) GetItem.

Eventos processados:
- INSERT: incrementa contador da região de origem
- REMOVE: decrementa contador (se transação deletada)
- MODIFY: não altera contador (update in-place não muda contagem)

Tabela de contadores (transaction_counters):
- PK: region (S) — ex: "us-east-1"
- SK: counter_key (S) — fixo "count"
- Attr: total_count (N) — contador atômico
"""

import json
import os
import logging
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

COUNTERS_TABLE = os.environ["COUNTERS_TABLE"]
REGION_NAME = os.environ["REGION_NAME"]

dynamodb = boto3.resource("dynamodb", region_name=REGION_NAME)
counters_table = dynamodb.Table(COUNTERS_TABLE)

COUNTER_KEY = "count"  # SK fixo para o item de contador


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_region_from_record(record: dict) -> str | None:
    """Extrai a região de origem do registro do stream."""
    # NewImage para INSERT/MODIFY, OldImage para REMOVE
    image = record.get("dynamodb", {}).get("NewImage") or record.get("dynamodb", {}).get("OldImage")
    if not image:
        return None
    region_attr = image.get("region_written")
    if not region_attr:
        return None
    return region_attr.get("S")


def update_counter(region: str, delta: int) -> bool:
    """Atualiza contador atômico na tabela de contadores."""
    try:
        counters_table.update_item(
            Key={"region": region, "counter_key": COUNTER_KEY},
            UpdateExpression="ADD total_count :delta",
            ExpressionAttributeValues={":delta": Decimal(str(delta))},
            ConditionExpression="attribute_exists(region)",  # Só atualiza se item existe
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # Item não existe — cria com put_item (idempotente)
            try:
                counters_table.put_item(
                    Item={
                        "region": region,
                        "counter_key": COUNTER_KEY,
                        "total_count": Decimal(str(max(0, delta))),
                    },
                    ConditionExpression="attribute_not_exists(region)",
                )
                return True
            except ClientError as e2:
                if e2.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    logger.error(f"Erro ao criar contador para {region}: {e2}")
                    return False
                # Race condition: outro processo criou — tenta update novamente
                return update_counter(region, delta)
        logger.error(f"Erro ao atualizar contador para {region}: {e}")
        return False


def lambda_handler(event, context):
    """Handler principal — processa batch de records do DynamoDB Stream."""
    logger.info(f"Processando {len(event.get('Records', []))} records do stream")

    processed = 0
    errors = 0

    for record in event.get("Records", []):
        event_name = record.get("eventName", "")
        region = get_region_from_record(record)

        if not region:
            logger.warning(f"Record sem region_written: {record.get('eventID')}")
            continue

        if event_name == "INSERT":
            # Nova transação — incrementa contador
            if update_counter(region, 1):
                processed += 1
            else:
                errors += 1

        elif event_name == "REMOVE":
            # Transação removida — decrementa contador (não deixa negativo)
            if update_counter(region, -1):
                processed += 1
            else:
                errors += 1

        elif event_name == "MODIFY":
            # Update in-place — não altera contagem
            processed += 1
            logger.debug(f"MODIFY ignorado para contagem: {record.get('eventID')}")

        else:
            logger.warning(f"Evento não reconhecido: {event_name}")

    logger.info(f"Stream processor concluído: {processed} processados, {errors} erros")

    return {
        "statusCode": 200,
        "processed": processed,
        "errors": errors,
    }