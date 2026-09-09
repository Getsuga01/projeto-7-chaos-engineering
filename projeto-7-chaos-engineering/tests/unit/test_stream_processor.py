"""
Testes unitários para o Stream Processor (stream_processor.py).
"""
import json
import os
import sys
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
import boto3
from moto import mock_aws

# Adiciona src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Configura variáveis de ambiente ANTES de importar
os.environ["COUNTERS_TABLE"] = "test-counters"
os.environ["REGION_NAME"] = "us-east-1"

from stream_processor import (
    lambda_handler,
    get_region_from_record,
    update_counter,
    COUNTER_KEY,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def setup_counters_table():
    """Cria tabela de contadores mockada."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-counters",
            KeySchema=[
                {"AttributeName": "region", "KeyType": "HASH"},
                {"AttributeName": "counter_key", "KeyType": "RANGE"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "region", "AttributeType": "S"},
                {"AttributeName": "counter_key", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # Insere contadores iniciais
        table.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 0})
        table.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 0})
        yield table


@pytest.fixture
def sample_insert_record():
    """Record de INSERT do DynamoDB Stream."""
    return {
        "eventID": "test-event-1",
        "eventName": "INSERT",
        "eventVersion": "1.1",
        "eventSource": "aws:dynamodb",
        "awsRegion": "us-east-1",
        "dynamodb": {
            "ApproximateCreationDateTime": 1704067200,
            "Keys": {"transaction_id": {"S": "txn-123"}},
            "NewImage": {
                "transaction_id": {"S": "txn-123"},
                "region_written": {"S": "us-east-1"},
                "amount": {"N": "100.50"},
                "description": {"S": "Test"},
                "created_at": {"S": "2024-01-01T00:00:00+00:00"},
                "created_at_epoch": {"N": "1704067200"},
            },
            "SequenceNumber": "12345",
            "SizeBytes": 200,
            "StreamViewType": "NEW_AND_OLD_IMAGES",
        },
        "eventSourceARN": "arn:aws:dynamodb:us-east-1:123456789012:table/test-transactions/stream/2024-01-01T00:00:00.000",
    }


@pytest.fixture
def sample_remove_record():
    """Record de REMOVE do DynamoDB Stream."""
    return {
        "eventID": "test-event-2",
        "eventName": "REMOVE",
        "eventVersion": "1.1",
        "eventSource": "aws:dynamodb",
        "awsRegion": "us-east-1",
        "dynamodb": {
            "ApproximateCreationDateTime": 1704067200,
            "Keys": {"transaction_id": {"S": "txn-123"}},
            "OldImage": {
                "transaction_id": {"S": "txn-123"},
                "region_written": {"S": "us-east-1"},
                "amount": {"N": "100.50"},
                "description": {"S": "Test"},
                "created_at": {"S": "2024-01-01T00:00:00+00:00"},
                "created_at_epoch": {"N": "1704067200"},
            },
            "SequenceNumber": "12346",
            "SizeBytes": 200,
            "StreamViewType": "NEW_AND_OLD_IMAGES",
        },
        "eventSourceARN": "arn:aws:dynamodb:us-east-1:123456789012:table/test-transactions/stream/2024-01-01T00:00:00.000",
    }


@pytest.fixture
def sample_modify_record():
    """Record de MODIFY do DynamoDB Stream."""
    return {
        "eventID": "test-event-3",
        "eventName": "MODIFY",
        "eventVersion": "1.1",
        "eventSource": "aws:dynamodb",
        "awsRegion": "us-east-1",
        "dynamodb": {
            "ApproximateCreationDateTime": 1704067200,
            "Keys": {"transaction_id": {"S": "txn-123"}},
            "NewImage": {
                "transaction_id": {"S": "txn-123"},
                "region_written": {"S": "us-east-1"},
                "amount": {"N": "200.00"},  # Valor alterado
                "description": {"S": "Updated"},
                "created_at": {"S": "2024-01-01T00:00:00+00:00"},
                "created_at_epoch": {"N": "1704067200"},
            },
            "OldImage": {
                "transaction_id": {"S": "txn-123"},
                "region_written": {"S": "us-east-1"},
                "amount": {"N": "100.50"},
                "description": {"S": "Test"},
                "created_at": {"S": "2024-01-01T00:00:00+00:00"},
                "created_at_epoch": {"N": "1704067200"},
            },
            "SequenceNumber": "12347",
            "SizeBytes": 200,
            "StreamViewType": "NEW_AND_OLD_IMAGES",
        },
        "eventSourceARN": "arn:aws:dynamodb:us-east-1:123456789012:table/test-transactions/stream/2024-01-01T00:00:00.000",
    }


# =============================================================================
# Testes: get_region_from_record
# =============================================================================

class TestGetRegionFromRecord:
    """Testes para extração de região do record."""

    def test_insert_record(self, sample_insert_record):
        """Testa extração de região de INSERT."""
        region = get_region_from_record(sample_insert_record)
        assert region == "us-east-1"

    def test_remove_record(self, sample_remove_record):
        """Testa extração de região de REMOVE (usa OldImage)."""
        region = get_region_from_record(sample_remove_record)
        assert region == "us-east-1"

    def test_modify_record(self, sample_modify_record):
        """Testa extração de região de MODIFY (usa NewImage)."""
        region = get_region_from_record(sample_modify_record)
        assert region == "us-east-1"

    def test_record_without_region(self):
        """Testa record sem region_written."""
        record = {"dynamodb": {"NewImage": {"transaction_id": {"S": "txn-1"}}}}
        region = get_region_from_record(record)
        assert region is None

    def test_record_without_image(self):
        """Testa record sem NewImage nem OldImage."""
        record = {"dynamodb": {}}
        region = get_region_from_record(record)
        assert region is None


# =============================================================================
# Testes: update_counter
# =============================================================================

class TestUpdateCounter:
    """Testes para atualização de contador."""

    def test_increment_counter(self, setup_counters_table):
        """Testa incremento de contador."""
        result = update_counter(setup_counters_table, "us-east-1", 1)
        assert result is True

        # Verifica valor
        item = setup_counters_table.get_item(Key={"region": "us-east-1", "counter_key": "count"})["Item"]
        assert item["total_count"] == Decimal("1")

    def test_decrement_counter(self, setup_counters_table):
        """Testa decremento de contador."""
        # Primeiro incrementa
        setup_counters_table.update_item(
            Key={"region": "us-east-1", "counter_key": "count"},
            UpdateExpression="ADD total_count :val",
            ExpressionAttributeValues={":val": Decimal("5")}
        )

        result = update_counter(setup_counters_table, "us-east-1", -1)
        assert result is True

        item = setup_counters_table.get_item(Key={"region": "us-east-1", "counter_key": "count"})["Item"]
        assert item["total_count"] == Decimal("4")

    def test_counter_not_negative(self, setup_counters_table):
        """Testa que contador não fica negativo."""
        # Contador em 0
        result = update_counter(setup_counters_table, "us-east-1", -1)
        assert result is True

        item = setup_counters_table.get_item(Key={"region": "us-east-1", "counter_key": "count"})["Item"]
        # O update_item com ADD permite negativo no DynamoDB, mas nossa lógica
        # de max(0, delta) no put_item condicional previne
        assert item["total_count"] >= Decimal("0")

    def test_creates_counter_if_not_exists(self, setup_counters_table):
        """Testa criação de contador se não existe (race condition)."""
        # Remove o contador
        setup_counters_table.delete_item(Key={"region": "us-east-1", "counter_key": "count"})

        result = update_counter(setup_counters_table, "us-east-1", 1)
        assert result is True

        item = setup_counters_table.get_item(Key={"region": "us-east-1", "counter_key": "count"})["Item"]
        assert item["total_count"] == Decimal("1")


# =============================================================================
# Testes: lambda_handler (Stream Processor)
# =============================================================================

class TestStreamProcessorHandler:
    """Testes para o handler principal do Stream Processor."""

    def test_process_insert_records(self, setup_counters_table, sample_insert_record):
        """Testa processamento de records INSERT."""
        event = {"Records": [sample_insert_record, sample_insert_record]}

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        assert response["processed"] == 2
        assert response["errors"] == 0

        # Verifica contador incrementado
        item = setup_counters_table.get_item(Key={"region": "us-east-1", "counter_key": "count"})["Item"]
        assert item["total_count"] == Decimal("2")

    def test_process_remove_records(self, setup_counters_table, sample_remove_record):
        """Testa processamento de records REMOVE."""
        # Primeiro incrementa
        setup_counters_table.update_item(
            Key={"region": "us-east-1", "counter_key": "count"},
            UpdateExpression="ADD total_count :val",
            ExpressionAttributeValues={":val": Decimal("5")}
        )

        event = {"Records": [sample_remove_record]}
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        assert response["processed"] == 1

        item = setup_counters_table.get_item(Key={"region": "us-east-1", "counter_key": "count"})["Item"]
        assert item["total_count"] == Decimal("4")

    def test_process_modify_records_ignored(self, setup_counters_table, sample_modify_record):
        """Testa que MODIFY não altera contador."""
        event = {"Records": [sample_modify_record]}

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        assert response["processed"] == 1

        # Contador não deve mudar
        item = setup_counters_table.get_item(Key={"region": "us-east-1", "counter_key": "count"})["Item"]
        assert item["total_count"] == Decimal("0")

    def test_process_mixed_records(self, setup_counters_table, sample_insert_record, sample_remove_record, sample_modify_record):
        """Testa processamento de batch misto."""
        event = {"Records": [
            sample_insert_record,
            sample_remove_record,
            sample_modify_record,
            sample_insert_record,
        ]}

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        assert response["processed"] == 4

        # 2 INSERT - 1 REMOVE = +1 líquido
        item = setup_counters_table.get_item(Key={"region": "us-east-1", "counter_key": "count"})["Item"]
        assert item["total_count"] == Decimal("1")

    def test_process_record_without_region(self, setup_counters_table):
        """Testa record sem region_written."""
        record = {
            "eventID": "test",
            "eventName": "INSERT",
            "dynamodb": {"NewImage": {"transaction_id": {"S": "txn-1"}}}
        }
        event = {"Records": [record]}

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        assert response["processed"] == 0  # Ignorado
        assert response["errors"] == 0

    def test_empty_records(self, setup_counters_table):
        """Testa batch vazio."""
        event = {"Records": []}
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        assert response["processed"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])