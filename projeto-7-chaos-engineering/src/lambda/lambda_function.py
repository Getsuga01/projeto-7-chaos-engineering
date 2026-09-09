"""
Projeto 7 — Lambda Handler: API de Transações e Experimentos de Chaos
======================================================================
Versão com Observabilidade e Comparação Cross-Region Nativa

Endpoints:
    POST   /transactions                    → Registra uma transação
    GET    /transactions/count              → Contagem local ou cross-region (?cross_region=true)
    POST   /admin/experiments               → Registra início de um experimento de chaos
    POST   /admin/experiments/{id}/resolve  → Marca experimento como resolvido, calcula RTO/RPO reais
    GET    /admin/experiments/{id}/report   → Relatório completo do experimento com status cross-region
    GET    /health                          → Health check e conectividade multi-região

Variáveis de ambiente:
    TRANSACTIONS_TABLE  — Nome da tabela DynamoDB de transações
    EXPERIMENTS_TABLE   — Nome da tabela DynamoDB de experimentos
    COUNTERS_TABLE      — Nome da tabela DynamoDB de contadores materializados
    REGION_NAME         — Região onde esta Lambda está rodando
    OTHER_REGION        — A outra região do setup ativo-ativo
"""

import json
import os
import uuid
import time
import logging
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TRANSACTIONS_TABLE = os.environ["TRANSACTIONS_TABLE"]
EXPERIMENTS_TABLE = os.environ["EXPERIMENTS_TABLE"]
COUNTERS_TABLE = os.environ["COUNTERS_TABLE"]
REGION_NAME = os.environ["REGION_NAME"]
OTHER_REGION = os.environ["OTHER_REGION"]

# Clientes DynamoDB: local e remoto (cross-region direto via Boto3)
dynamodb_local = boto3.resource("dynamodb", region_name=REGION_NAME)
dynamodb_remote = boto3.resource("dynamodb", region_name=OTHER_REGION)
cloudwatch = boto3.client("cloudwatch", region_name=REGION_NAME)

transactions_table_local = dynamodb_local.Table(TRANSACTIONS_TABLE)
transactions_table_remote = dynamodb_remote.Table(TRANSACTIONS_TABLE)

experiments_table_local = dynamodb_local.Table(EXPERIMENTS_TABLE)
experiments_table_remote = dynamodb_remote.Table(EXPERIMENTS_TABLE)

counters_table_local = dynamodb_local.Table(COUNTERS_TABLE)
counters_table_remote = dynamodb_remote.Table(COUNTERS_TABLE)

COUNTER_KEY = "count"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DecimalEncoder(json.JSONEncoder):
    """Serializa Decimal do DynamoDB para float/int no JSON."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def json_response(status_code: int, body: dict) -> dict:
    """Constrói a resposta HTTP para o API Gateway v2."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "X-Region": REGION_NAME,
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def now_iso() -> str:
    """Retorna o timestamp atual em ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


def now_epoch() -> int:
    """Retorna o timestamp atual em epoch seconds."""
    return int(time.time())


def get_counter_count(table, region: str) -> int:
    """Lê contador materializado da tabela de contadores — O(1) GetItem."""
    try:
        response = table.get_item(Key={"region": region, "counter_key": COUNTER_KEY})
        if "Item" in response:
            return int(response["Item"].get("total_count", 0))
        # Contador não existe ainda — retorna 0 (tabela vazia ou stream processor não processou)
        return 0
    except ClientError as e:
        logger.error(f"Erro ao ler contador para região {region}: {e}")
        return -1


def get_table_count(table) -> int:
    """
    DEPRECATED: Mantido para compatibilidade.
    Use get_counter_count() para performance O(1).
    """
    try:
        response = table.scan(Select="COUNT")
        count = response.get("Count", 0)

        while "LastEvaluatedKey" in response:
            response = table.scan(
                Select="COUNT",
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            count += response.get("Count", 0)
        return count
    except ClientError as e:
        logger.error(f"Erro ao contar itens na tabela {table.table_name}: {e}")
        return -1


def emit_metric(metric_name: str, value: float, unit: str = "Count") -> None:
    """Emite uma métrica customizada para o CloudWatch."""
    try:
        cloudwatch.put_metric_data(
            Namespace=os.environ.get("PROJECT_NAME", "chaos-lab"),
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Dimensions": [
                        {"Name": "Region", "Value": REGION_NAME},
                    ],
                    "Value": value,
                    "Unit": unit,
                    "Timestamp": datetime.now(timezone.utc),
                }
            ],
        )
    except Exception as e:
        logger.warning(f"Falha ao emitir métrica {metric_name}: {e}")


def _format_duration(seconds) -> str:
    """Formata duração em segundos para string legível."""
    if seconds is None:
        return "N/A"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remaining = seconds % 60
    return f"{minutes}m {remaining}s"


# ---------------------------------------------------------------------------
# Handlers por endpoint
# ---------------------------------------------------------------------------

def handle_post_transaction(body: dict) -> dict:
    """
    POST /transactions
    Registra uma nova transação no livro-razão na região local.
    """
    transaction_id = str(uuid.uuid4())
    amount = body.get("amount", 0)
    description = body.get("description", "")

    item = {
        "transaction_id": transaction_id,
        "region_written": REGION_NAME,
        "amount": Decimal(str(amount)),
        "description": description,
        "created_at": now_iso(),
        "created_at_epoch": now_epoch(),
        "observed_in_other_region_at": None,
    }

    transactions_table_local.put_item(Item=item)

    logger.info(f"Transação criada: {transaction_id} na região {REGION_NAME}")

    return json_response(201, {
        "message": "Transação registrada com sucesso",
        "transaction_id": transaction_id,
        "region_written": REGION_NAME,
        "created_at": item["created_at"],
    })


def handle_get_transactions_count(query_params: dict) -> dict:
    """
    GET /transactions/count
    Retorna a contagem de transações via contador materializado (O(1)).
    Se query param ?cross_region=true for passado,
    consulta também a réplica na outra região e calcula a divergência instantânea.
    """
    include_cross_region = query_params.get("cross_region", "").lower() in ("true", "1", "yes")

    local_count = get_counter_count(counters_table_local, REGION_NAME)
    if local_count >= 0:
        emit_metric("TransactionCount", local_count)

    response_data = {
        "region": REGION_NAME,
        "count": local_count,
        "timestamp": now_iso(),
    }

    if include_cross_region:
        remote_count = get_counter_count(counters_table_remote, OTHER_REGION)
        divergence = abs(local_count - remote_count) if (local_count >= 0 and remote_count >= 0) else None

        response_data["cross_region"] = {
            "remote_region": OTHER_REGION,
            "remote_count": remote_count,
            "divergence": divergence,
            "is_in_sync": divergence == 0,
        }

    return json_response(200, response_data)


def handle_post_experiment(body: dict, client_id: str | None) -> dict:
    """
    POST /admin/experiments
    Registra o início de um experimento de chaos.
    Captura as contagens baseline em AMBAS as regiões para medições precisas.
    """
    experiment_id = str(uuid.uuid4())

    count_a = get_counter_count(counters_table_local, REGION_NAME)
    count_b = get_counter_count(counters_table_remote, OTHER_REGION)

    item = {
        "experiment_id": experiment_id,
        "fault_type": body.get("fault_type", "pause-replication"),
        "notes": body.get("notes", ""),
        "started_at": now_iso(),
        "started_at_epoch": now_epoch(),
        "fault_resolved_at": None,
        "converged_at": None,
        "measured_rto_seconds": None,
        "measured_rpo_records_affected": None,
        "status": "RUNNING",
        "region_a": REGION_NAME,
        "region_b": OTHER_REGION,
        "baseline_count_region_a": count_a,
        "baseline_count_region_b": count_b,
        "initial_divergence": abs(count_a - count_b) if (count_a >= 0 and count_b >= 0) else 0,
        "created_by": client_id,
    }

    experiments_table_local.put_item(Item=item)

    logger.info(f"Experimento iniciado: {experiment_id} — tipo: {item['fault_type']} — por: {client_id}")

    return json_response(201, {
        "message": "Experimento registrado com sucesso — pronto para disparar FIS",
        "experiment_id": experiment_id,
        "status": "RUNNING",
        "started_at": item["started_at"],
        "baselines": {
            REGION_NAME: count_a,
            OTHER_REGION: count_b,
        },
        "next_step": "Dispare o experimento no FIS e, após retomar a replicação, chame POST /admin/experiments/{id}/resolve",
    })


def handle_post_experiment_resolve(experiment_id: str, client_id: str | None) -> dict:
    """
    POST /admin/experiments/{id}/resolve
    Marca o experimento como resolvido e calcula RTO e RPO reais comparando
    ambas as regiões em tempo real.
    """
    response = experiments_table_local.get_item(Key={"experiment_id": experiment_id})

    if "Item" not in response:
        return json_response(404, {"error": f"Experimento {experiment_id} não encontrado"})

    experiment = response["Item"]

    fault_resolved_at = now_iso()
    fault_resolved_at_epoch = now_epoch()

    # Contagens em ambas as regiões no momento da resolução (via contador materializado)
    count_local = get_counter_count(counters_table_local, REGION_NAME)
    count_remote = get_counter_count(counters_table_remote, OTHER_REGION)

    # Divergência no instante de encerramento da falha (RPO real: dados em atraso)
    divergence = abs(count_local - count_remote) if (count_local >= 0 and count_remote >= 0) else 0

    started_epoch = experiment.get("started_at_epoch", fault_resolved_at_epoch)
    duration_seconds = fault_resolved_at_epoch - int(started_epoch)

    # Se as contagens já bateram, convergência imediata; senão convergência pendente
    is_converged = (divergence == 0)
    converged_at = fault_resolved_at if is_converged else None

    update_expr = (
        "SET #status = :status, "
        "fault_resolved_at = :resolved_at, "
        "fault_resolved_at_epoch = :resolved_epoch, "
        "converged_at = :converged_at, "
        "measured_rto_seconds = :rto, "
        "measured_rpo_records_affected = :rpo, "
        "final_count_region_a = :count_a, "
        "final_count_region_b = :count_b, "
        "is_converged = :converged, "
        "resolved_by = :resolved_by"
    )

    expr_values = {
        ":status": "RESOLVED",
        ":resolved_at": fault_resolved_at,
        ":resolved_epoch": fault_resolved_at_epoch,
        ":converged_at": converged_at,
        ":rto": duration_seconds,
        ":rpo": divergence,
        ":count_a": count_local,
        ":count_b": count_remote,
        ":converged": is_converged,
        ":resolved_by": client_id,
    }

    experiments_table_local.update_item(
        Key={"experiment_id": experiment_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=expr_values,
    )

    logger.info(
        f"Experimento {experiment_id} resolvido — RTO: {duration_seconds}s, RPO: {divergence} registros"
    )

    return json_response(200, {
        "message": "Experimento resolvido com sucesso",
        "experiment_id": experiment_id,
        "status": "RESOLVED",
        "fault_resolved_at": fault_resolved_at,
        "measured_rto_seconds": duration_seconds,
        "measured_rpo_records_affected": divergence,
        "counts": {
            REGION_NAME: count_local,
            OTHER_REGION: count_remote,
            "divergence": divergence,
            "is_converged": is_converged,
        },
    })


def handle_get_experiment_report(experiment_id: str, client_id: str | None) -> dict:
    """
    GET /admin/experiments/{id}/report
    Retorna o relatório completo do Game Day, incluindo o status de sincronização
    ao vivo entre as duas regiões.
    """
    response = experiments_table_local.get_item(Key={"experiment_id": experiment_id})

    if "Item" not in response:
        return json_response(404, {"error": f"Experimento {experiment_id} não encontrado"})

    experiment = response["Item"]

    # Consulta estado atual ao vivo para verificar convergência (via contador materializado)
    live_count_local = get_counter_count(counters_table_local, REGION_NAME)
    live_count_remote = get_counter_count(counters_table_remote, OTHER_REGION)
    live_divergence = (
        abs(live_count_local - live_count_remote)
        if (live_count_local >= 0 and live_count_remote >= 0)
        else None
    )

    report = {
        "report_title": f"Game Day Report — {experiment.get('fault_type', 'N/A')}",
        "experiment_id": experiment_id,
        "status": experiment.get("status", "UNKNOWN"),
        "fault_type": experiment.get("fault_type"),
        "notes": experiment.get("notes"),
        "regions": {
            "primary": experiment.get("region_a", REGION_NAME),
            "secondary": experiment.get("region_b", OTHER_REGION),
        },
        "timeline": {
            "started_at": experiment.get("started_at"),
            "fault_resolved_at": experiment.get("fault_resolved_at"),
            "converged_at": experiment.get("converged_at"),
        },
        "measurements": {
            "rto_seconds": experiment.get("measured_rto_seconds"),
            "rto_human": _format_duration(experiment.get("measured_rto_seconds")),
            "rpo_records_affected": experiment.get("measured_rpo_records_affected"),
        },
        "historical_counts": {
            "baseline_region_a": experiment.get("baseline_count_region_a"),
            "baseline_region_b": experiment.get("baseline_count_region_b"),
            "final_count_region_a": experiment.get("final_count_region_a"),
            "final_count_region_b": experiment.get("final_count_region_b"),
        },
        "live_cross_region_status": {
            "current_count_local": live_count_local,
            "current_count_remote": live_count_remote,
            "current_divergence": live_divergence,
            "is_currently_synchronized": live_divergence == 0,
        },
        "generated_at": now_iso(),
        "generated_in_region": REGION_NAME,
    }

    return json_response(200, report)


def handle_health() -> dict:
    """GET /health — Diagnóstico regional e conectividade cross-region."""
    remote_accessible = False
    try:
        transactions_table_remote.load()
        remote_accessible = True
    except Exception as e:
        logger.warning(f"Não foi possível acessar a tabela remota em {OTHER_REGION}: {e}")

    return json_response(200, {
        "status": "healthy",
        "region_local": REGION_NAME,
        "region_remote": OTHER_REGION,
        "cross_region_access": remote_accessible,
        "timestamp": now_iso(),
        "tables": {
            "transactions": TRANSACTIONS_TABLE,
            "experiments": EXPERIMENTS_TABLE,
        },
    })


# ---------------------------------------------------------------------------
# Router — ponto de entrada principal
# ---------------------------------------------------------------------------

def get_authorizer_context(event: dict) -> dict:
    """Extrai contexto do authorizer (client_id, scope) do request."""
    # HTTP API v2: authorizer context vem em requestContext.authorizer.lambda
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})
    lambda_auth = authorizer.get("lambda", {})
    return lambda_auth


def lambda_handler(event, context):
    """Handler principal da Lambda. Roteia requisições HTTP do API Gateway v2."""
    logger.info(f"Evento recebido: {json.dumps(event, default=str)}")

    route_key = event.get("routeKey", "")
    raw_path = event.get("rawPath", "")
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path_params = event.get("pathParameters", {}) or {}
    query_params = event.get("queryStringParameters", {}) or {}

    # Contexto do authorizer (para endpoints protegidos)
    auth_context = get_authorizer_context(event)
    client_id = auth_context.get("client_id")
    scope = auth_context.get("scope")

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            return json_response(400, {"error": "Body inválido — esperado JSON válido"})

    try:
        if route_key == "POST /transactions":
            return handle_post_transaction(body)

        elif route_key == "GET /transactions/count":
            return handle_get_transactions_count(query_params)

        elif route_key == "POST /auth/token":
            # Token endpoint é público (handled pelo authorizer Lambda)
            return json_response(404, {"error": "Rota não encontrada"})

        elif route_key == "POST /admin/experiments":
            return handle_post_experiment(body, client_id)

        elif route_key == "POST /admin/experiments/{id}/resolve":
            experiment_id = path_params.get("id", "")
            if not experiment_id:
                return json_response(400, {"error": "ID do experimento é obrigatório"})
            return handle_post_experiment_resolve(experiment_id, client_id)

        elif route_key == "GET /admin/experiments/{id}/report":
            experiment_id = path_params.get("id", "")
            if not experiment_id:
                return json_response(400, {"error": "ID do experimento é obrigatório"})
            return handle_get_experiment_report(experiment_id, client_id)

        elif route_key == "GET /health":
            return handle_health()

        else:
            return json_response(404, {
                "error": "Rota não encontrada",
                "route_key": route_key,
                "raw_path": raw_path,
                "method": http_method,
            })

    except Exception as e:
        logger.exception(f"Erro não tratado na Lambda: {e}")
        return json_response(500, {
            "error": "Erro interno do servidor",
            "message": str(e),
            "region": REGION_NAME,
        })
