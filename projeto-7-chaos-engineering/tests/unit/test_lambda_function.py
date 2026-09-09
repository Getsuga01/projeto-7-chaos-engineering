"""
Testes unitários para o Lambda Handler principal (lambda_function.py).
Usa moto para mockar DynamoDB e CloudWatch.
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


# Configura variáveis de ambiente ANTES de importar o módulo
os.environ["TRANSACTIONS_TABLE"] = "test-transactions"
os.environ["EXPERIMENTS_TABLE"] = "test-experiments"
os.environ["COUNTERS_TABLE"] = "test-counters"
os.environ["REGION_NAME"] = "us-east-1"
os.environ["OTHER_REGION"] = "sa-east-1"
os.environ["ENVIRONMENT"] = "sandbox"
os.environ["PROJECT_NAME"] = "chaos-lab"

# Importa depois de configurar env vars
from lambda_function import (
    lambda_handler,
    handle_post_transaction,
    handle_get_transactions_count,
    handle_post_experiment,
    handle_post_experiment_resolve,
    handle_get_experiment_report,
    handle_health,
    get_counter_count,
    json_response,
    DecimalEncoder,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def setup_dynamodb():
    """Cria tabelas DynamoDB mockadas para testes."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # Tabela de transações
        transactions_table = dynamodb.create_table(
            TableName="test-transactions",
            KeySchema=[{"AttributeName": "transaction_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "transaction_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
            StreamSpecification={
                "StreamEnabled": True,
                "StreamViewType": "NEW_AND_OLD_IMAGES"
            }
        )

        # Tabela de experimentos
        experiments_table = dynamodb.create_table(
            TableName="test-experiments",
            KeySchema=[{"AttributeName": "experiment_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "experiment_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Tabela de contadores
        counters_table = dynamodb.create_table(
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
        counters_table.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 0})
        counters_table.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 0})

        yield {
            "transactions": transactions_table,
            "experiments": experiments_table,
            "counters": counters_table,
            "dynamodb": dynamodb,
        }


@pytest.fixture
def api_gateway_event():
    """Evento base do API Gateway HTTP API v2."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": "/",
        "rawQueryString": "",
        "headers": {
            "content-type": "application/json",
            "host": "test.execute-api.us-east-1.amazonaws.com",
        },
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "test-api",
            "domainName": "test.execute-api.us-east-1.amazonaws.com",
            "domainPrefix": "test",
            "http": {
                "method": "POST",
                "path": "/",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "test-agent",
            },
            "requestId": "test-request-id",
            "routeKey": "$default",
            "stage": "$default",
            "time": "01/Jan/2024:00:00:00 +0000",
            "timeEpoch": 1704067200000,
        },
        "isBase64Encoded": False,
    }


@pytest.fixture
def auth_context():
    """Contexto de autorizador simulado."""
    return {
        "client_id": "test-client",
        "scope": "admin",
    }


# =============================================================================
# Testes: Helpers
# =============================================================================

class TestHelpers:
    """Testes para funções auxiliares."""

    def test_json_response(self):
        """Testa construção de resposta HTTP."""
        response = json_response(200, {"message": "ok"})
        assert response["statusCode"] == 200
        assert response["headers"]["Content-Type"] == "application/json"
        assert "message" in response["body"]

    def test_decimal_encoder(self):
        """Testa serialização de Decimal."""
        encoder = DecimalEncoder()
        assert encoder.default(Decimal("10")) == 10
        assert encoder.default(Decimal("10.5")) == 10.5
        assert encoder.default("string") == "string"  # fallback


# =============================================================================
# Testes: get_counter_count
# =============================================================================

class TestGetCounterCount:
    """Testes para leitura de contadores materializados."""

    def test_get_counter_count_exists(self, setup_dynamodb):
        """Testa leitura de contador existente."""
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 42})

        count = get_counter_count(counters, "us-east-1")
        assert count == 42

    def test_get_counter_count_not_exists(self, setup_dynamodb):
        """Testa leitura de contador inexistente (retorna 0)."""
        counters = setup_dynamodb["counters"]
        # Não insere o item

        count = get_counter_count(counters, "us-east-1")
        assert count == 0

    def test_get_counter_count_error(self, setup_dynamodb):
        """Testa tratamento de erro ao ler contador."""
        # Tabela inexistente
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        fake_table = dynamodb.Table("non-existent-table")

        count = get_counter_count(fake_table, "us-east-1")
        assert count == -1


# =============================================================================
# Testes: handle_post_transaction
# =============================================================================

class TestPostTransaction:
    """Testes para POST /transactions."""

    def test_post_transaction_success(self, setup_dynamodb):
        """Testa criação de transação bem-sucedida."""
        body = {"amount": 100.50, "description": "Test transaction"}
        response = handle_post_transaction(body)

        assert response["statusCode"] == 201
        body_data = json.loads(response["body"])
        assert body_data["message"] == "Transação registrada com sucesso"
        assert "transaction_id" in body_data
        assert body_data["region_written"] == "us-east-1"

        # Verifica se item foi salvo no DynamoDB
        transactions = setup_dynamodb["transactions"]
        items = transactions.scan()["Items"]
        assert len(items) == 1
        assert items[0]["amount"] == Decimal("100.50")
        assert items[0]["description"] == "Test transaction"
        assert items[0]["region_written"] == "us-east-1"

    def test_post_transaction_minimal_body(self, setup_dynamodb):
        """Testa criação com body mínimo."""
        body = {}
        response = handle_post_transaction(body)

        assert response["statusCode"] == 201
        body_data = json.loads(response["body"])
        assert "transaction_id" in body_data

    def test_post_transaction_increments_counter(self, setup_dynamodb):
        """Testa se contador é incrementado (via stream processor seria, mas aqui verifica item)."""
        body = {"amount": 50.0}
        handle_post_transaction(body)

        # O stream processor incrementaria o contador em produção
        # Aqui apenas verificamos que a transação foi salva
        transactions = setup_dynamodb["transactions"]
        items = transactions.scan()["Items"]
        assert len(items) == 1


# =============================================================================
# Testes: handle_get_transactions_count
# =============================================================================

class TestGetTransactionsCount:
    """Testes para GET /transactions/count."""

    def test_get_count_local_only(self, setup_dynamodb):
        """Testa contagem apenas local."""
        # Insere algumas transações
        transactions = setup_dynamodb["transactions"]
        for i in range(5):
            transactions.put_item(Item={
                "transaction_id": f"txn-{i}",
                "region_written": "us-east-1",
                "amount": Decimal(str(i * 10)),
                "description": f"Test {i}",
                "created_at": "2024-01-01T00:00:00+00:00",
                "created_at_epoch": 1704067200,
                "observed_in_other_region_at": None,
            })

        # Atualiza contador manualmente (simula stream processor)
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 5})

        event = {"queryStringParameters": {}}
        response = handle_get_transactions_count(event.get("queryStringParameters", {}))

        assert response["statusCode"] == 200
        body_data = json.loads(response["body"])
        assert body_data["count"] == 5
        assert body_data["region"] == "us-east-1"
        assert "cross_region" not in body_data

    def test_get_count_cross_region(self, setup_dynamodb):
        """Testa contagem cross-region com divergência."""
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 10})
        counters.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 7})

        event = {"queryStringParameters": {"cross_region": "true"}}
        response = handle_get_transactions_count(event.get("queryStringParameters", {}))

        assert response["statusCode"] == 200
        body_data = json.loads(response["body"])
        assert body_data["count"] == 10
        assert body_data["cross_region"]["remote_count"] == 7
        assert body_data["cross_region"]["divergence"] == 3
        assert body_data["cross_region"]["is_in_sync"] is False

    def test_get_count_cross_region_in_sync(self, setup_dynamodb):
        """Testa contagem cross-region sincronizada."""
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 10})
        counters.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 10})

        event = {"queryStringParameters": {"cross_region": "true"}}
        response = handle_get_transactions_count(event.get("queryStringParameters", {}))

        body_data = json.loads(response["body"])
        assert body_data["cross_region"]["divergence"] == 0
        assert body_data["cross_region"]["is_in_sync"] is True


# =============================================================================
# Testes: handle_post_experiment
# =============================================================================

class TestPostExperiment:
    """Testes para POST /admin/experiments."""

    def test_post_experiment_success(self, setup_dynamodb):
        """Testa registro de experimento bem-sucedido."""
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 100})
        counters.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 100})

        body = {"fault_type": "pause-replication", "notes": "Test experiment"}
        response = handle_post_experiment(body, "test-client")

        assert response["statusCode"] == 201
        body_data = json.loads(response["body"])
        assert body_data["status"] == "RUNNING"
        assert "experiment_id" in body_data
        assert body_data["baselines"]["us-east-1"] == 100
        assert body_data["baselines"]["sa-east-1"] == 100

        # Verifica se experimento foi salvo
        experiments = setup_dynamodb["experiments"]
        items = experiments.scan()["Items"]
        assert len(items) == 1
        assert items[0]["fault_type"] == "pause-replication"
        assert items[0]["notes"] == "Test experiment"
        assert items[0]["created_by"] == "test-client"

    def test_post_experiment_default_fault_type(self, setup_dynamodb):
        """Testa tipo de falha padrão."""
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 0})
        counters.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 0})

        body = {"notes": "Test"}
        response = handle_post_experiment(body, "test-client")

        body_data = json.loads(response["body"])
        assert body_data["status"] == "RUNNING"


# =============================================================================
# Testes: handle_post_experiment_resolve
# =============================================================================

class TestPostExperimentResolve:
    """Testes para POST /admin/experiments/{id}/resolve."""

    def test_resolve_experiment_success(self, setup_dynamodb):
        """Testa resolução de experimento bem-sucedida."""
        # Setup: cria experimento
        experiments = setup_dynamodb["experiments"]
        experiment_id = "test-exp-123"
        experiments.put_item(Item={
            "experiment_id": experiment_id,
            "fault_type": "pause-replication",
            "notes": "Test",
            "started_at": "2024-01-01T00:00:00+00:00",
            "started_at_epoch": 1704067200,
            "status": "RUNNING",
            "region_a": "us-east-1",
            "region_b": "sa-east-1",
            "baseline_count_region_a": 100,
            "baseline_count_region_b": 100,
            "initial_divergence": 0,
        })

        # Contadores no momento da resolução (com divergência)
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 110})
        counters.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 105})

        response = handle_post_experiment_resolve(experiment_id, "test-client")

        assert response["statusCode"] == 200
        body_data = json.loads(response["body"])
        assert body_data["status"] == "RESOLVED"
        assert body_data["measured_rpo_records_affected"] == 5  # 110 - 105
        assert body_data["counts"]["divergence"] == 5

        # Verifica atualização no DynamoDB
        updated = experiments.get_item(Key={"experiment_id": experiment_id})["Item"]
        assert updated["status"] == "RESOLVED"
        assert updated["measured_rpo_records_affected"] == 5
        assert updated["resolved_by"] == "test-client"

    def test_resolve_experiment_not_found(self, setup_dynamodb):
        """Testa resolução de experimento inexistente."""
        response = handle_post_experiment_resolve("non-existent", "test-client")
        assert response["statusCode"] == 404
        body_data = json.loads(response["body"])
        assert "não encontrado" in body_data["error"]


# =============================================================================
# Testes: handle_get_experiment_report
# =============================================================================

class TestGetExperimentReport:
    """Testes para GET /admin/experiments/{id}/report."""

    def test_get_report_success(self, setup_dynamodb):
        """Testa obtenção de relatório."""
        experiments = setup_dynamodb["experiments"]
        experiment_id = "test-exp-123"
        experiments.put_item(Item={
            "experiment_id": experiment_id,
            "fault_type": "pause-replication",
            "notes": "Test experiment",
            "started_at": "2024-01-01T00:00:00+00:00",
            "started_at_epoch": 1704067200,
            "fault_resolved_at": "2024-01-01T00:10:00+00:00",
            "fault_resolved_at_epoch": 1704067800,
            "converged_at": "2024-01-01T00:12:00+00:00",
            "measured_rto_seconds": 120,
            "measured_rpo_records_affected": 5,
            "status": "RESOLVED",
            "region_a": "us-east-1",
            "region_b": "sa-east-1",
            "baseline_count_region_a": 100,
            "baseline_count_region_b": 100,
            "final_count_region_a": 110,
            "final_count_region_b": 105,
            "is_converged": True,
            "created_by": "client-1",
            "resolved_by": "client-2",
        })

        # Contadores atuais
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 115})
        counters.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 115})

        response = handle_get_experiment_report(experiment_id, "test-client")

        assert response["statusCode"] == 200
        body_data = json.loads(response["body"])
        assert body_data["experiment_id"] == experiment_id
        assert body_data["status"] == "RESOLVED"
        assert body_data["measurements"]["rto_seconds"] == 120
        assert body_data["measurements"]["rpo_records_affected"] == 5
        assert body_data["live_cross_region_status"]["is_currently_synchronized"] is True
        assert body_data["historical_counts"]["baseline_region_a"] == 100

    def test_get_report_not_found(self, setup_dynamodb):
        """Testa relatório de experimento inexistente."""
        response = handle_get_experiment_report("non-existent", "test-client")
        assert response["statusCode"] == 404


# =============================================================================
# Testes: handle_health
# =============================================================================

class TestHealth:
    """Testes para GET /health."""

    def test_health_check(self, setup_dynamodb):
        """Testa health check básico."""
        response = handle_health()
        assert response["statusCode"] == 200
        body_data = json.loads(response["body"])
        assert body_data["status"] == "healthy"
        assert body_data["region_local"] == "us-east-1"
        assert body_data["region_remote"] == "sa-east-1"
        assert "tables" in body_data


# =============================================================================
# Testes: Lambda Handler (Router)
# =============================================================================

class TestLambdaHandler:
    """Testes para o router principal (lambda_handler)."""

    def make_event(self, route_key, method="POST", body=None, path_params=None, query_params=None, auth_ctx=None):
        """Helper para criar evento API Gateway."""
        event = {
            "version": "2.0",
            "routeKey": route_key,
            "rawPath": route_key.split(" ")[1] if " " in route_key else "/",
            "requestContext": {
                "http": {"method": method},
                "authorizer": {"lambda": auth_ctx} if auth_ctx else {},
            },
            "pathParameters": path_params or {},
            "queryStringParameters": query_params or {},
        }
        if body:
            event["body"] = json.dumps(body)
        return event

    def test_post_transaction_route(self, setup_dynamodb):
        """Testa roteamento POST /transactions."""
        event = self.make_event("POST /transactions", body={"amount": 100})
        response = lambda_handler(event, None)
        assert response["statusCode"] == 201

    def test_get_transactions_count_route(self, setup_dynamodb):
        """Testa roteamento GET /transactions/count."""
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 5})

        event = self.make_event("GET /transactions/count", method="GET")
        response = lambda_handler(event, None)
        assert response["statusCode"] == 200
        body_data = json.loads(response["body"])
        assert body_data["count"] == 5

    def test_post_experiment_route_with_auth(self, setup_dynamodb):
        """Testa roteamento POST /admin/experiments com authorizer."""
        counters = setup_dynamodb["counters"]
        counters.put_item(Item={"region": "us-east-1", "counter_key": "count", "total_count": 0})
        counters.put_item(Item={"region": "sa-east-1", "counter_key": "count", "total_count": 0})

        event = self.make_event(
            "POST /admin/experiments",
            body={"notes": "Test"},
            auth_ctx={"client_id": "test-client", "scope": "admin"}
        )
        response = lambda_handler(event, None)
        assert response["statusCode"] == 201

    def test_unknown_route_returns_404(self, setup_dynamodb):
        """Testa rota desconhecida retorna 404."""
        event = self.make_event("GET /unknown")
        response = lambda_handler(event, None)
        assert response["statusCode"] == 404
        body_data = json.loads(response["body"])
        assert body_data["error"] == "Rota não encontrada"

    def test_invalid_json_body(self, setup_dynamodb):
        """Testa body JSON inválido."""
        event = self.make_event("POST /transactions")
        event["body"] = "invalid json"
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body_data = json.loads(response["body"])
        assert "JSON" in body_data["error"]


# =============================================================================
# Execução direta
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])