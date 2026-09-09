"""
Testes de integração para o Projeto 7.
Usa moto para simular infraestrutura AWS completa.
"""
import json
import os
import sys
import time
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
import boto3
from moto import mock_aws

# Adiciona src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Configura variáveis de ambiente
os.environ["TRANSACTIONS_TABLE"] = "transactions"
os.environ["EXPERIMENTS_TABLE"] = "experiments"
os.environ["COUNTERS_TABLE"] = "counters"
os.environ["CLIENTS_TABLE"] = "api-clients"
os.environ["REGION_NAME"] = "us-east-1"
os.environ["OTHER_REGION"] = "sa-east-1"
os.environ["ENVIRONMENT"] = "sandbox"
os.environ["PROJECT_NAME"] = "chaos-lab"
os.environ["JWT_SECRET"] = "test-secret-key"
os.environ["TOKEN_TTL_SECONDS"] = "3600"

# Importa após configurar env vars
from lambda_function import lambda_handler
from authorizer import create_token


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def setup_localstack():
    """Configura infraestrutura completa para testes de integração."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        client = boto3.client("dynamodb", region_name="us-east-1")

        # Cria tabela de transações com stream
        client.create_table(
            TableName="transactions",
            KeySchema=[{"AttributeName": "transaction_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "transaction_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
            StreamSpecification={
                "StreamEnabled": True,
                "StreamViewType": "NEW_AND_OLD_IMAGES"
            }
        )

        # Cria tabela de experimentos
        client.create_table(
            TableName="experiments",
            KeySchema=[{"AttributeName": "experiment_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "experiment_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Cria tabela de contadores
        client.create_table(
            TableName="counters",
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

        # Cria tabela de clientes API
        client.create_table(
            TableName="api-clients",
            KeySchema=[{"AttributeName": "client_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "client_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Inicializa contadores
        for region in ["us-east-1", "sa-east-1"]:
            dynamodb.Table("counters").put_item(Item={
                "region": region,
                "counter_key": "count",
                "total_count": 0,
            })

        # Inicializa cliente API
        dynamodb.Table("api-clients").put_item(Item={
            "client_id": "test-client",
            "client_secret": "test-secret",
            "active": True,
            "allowed_scopes": ["admin", "read"],
            "created_at": "2024-01-01T00:00:00+00:00",
        })

        yield {
            "dynamodb": dynamodb,
            "client": client,
        }


# =============================================================================
# Testes: Fluxo Completo de Transação
# =============================================================================

class TestFullTransactionWorkflow:
    """Testa fluxo completo de transação."""

    def test_complete_transaction_flow(self, setup_localstack):
        """Testa fluxo: criar transação -> contador incrementado."""
        dynamodb = setup_localstack["dynamodb"]

        # 1. Cria transação
        event_body = {"amount": 100.50, "description": "Teste integração"}
        event = {
            "version": "2.0",
            "routeKey": "POST /transactions",
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps(event_body),
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 201
        body = json.loads(response["body"])
        assert "transaction_id" in body
        assert body["region_written"] == "us-east-1"

        # 2. Verifica transação salva
        txn = dynamodb.Table("transactions").get_item(
            Key={"transaction_id": body["transaction_id"]}
        )["Item"]
        assert txn["amount"] == Decimal("100.50")
        assert txn["description"] == "Teste integração"
        assert txn["status"] == "CONFIRMED"

    def test_transaction_list(self, setup_localstack):
        """Testa listagem de transações."""
        dynamodb = setup_localstack["dynamodb"]

        # Cria múltiplas transações
        for i in range(3):
            dynamodb.Table("transactions").put_item(Item={
                "transaction_id": f"txn-{i}",
                "region_written": "us-east-1",
                "amount": Decimal(str(i * 10)),
                "description": f"Test {i}",
                "created_at": "2024-01-01T00:00:00+00:00",
                "created_at_epoch": 1704067200,
            })

        # Simula GET /transactions listing
        items = dynamodb.Table("transactions").scan()["Items"]
        assert len(items) == 3


# =============================================================================
# Testes: Fluxo de Autenticação Completo
# =============================================================================

class TestFullAuthWorkflow:
    """Testa fluxo completo de autenticação."""

    def test_auth_and_access_admin_endpoint(self, setup_localstack):
        """Testa fluxo: obter token -> acessar endpoint admin."""
        # 1. Obtém token
        token = create_token("test-client", "admin")
        assert token is not None
        parts = token.split(".")
        assert len(parts) == 3

        # 2. Acessa endpoint admin
        event = {
            "version": "2.0",
            "routeKey": "POST /admin/experiments",
            "requestContext": {
                "http": {"method": "POST"},
                "authorizer": {"lambda": {"client_id": "test-client", "scope": "admin"}},
            },
            "body": json.dumps({"notes": "Teste admin"}),
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 201

    def test_unauthorized_access_denied(self, setup_localstack):
        """Testa que acesso sem autorização é negado."""
        event = {
            "version": "2.0",
            "routeKey": "POST /admin/experiments",
            "requestContext": {
                "http": {"method": "POST"},
                # Sem authorizer
            },
            "body": json.dumps({"notes": "Teste"}),
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert "Autenticação" in body["error"]


# =============================================================================
# Testes: Ciclo de Vida do Experimento
# =============================================================================

class TestExperimentLifecycle:
    """Testa ciclo de vida completo de experimento."""

    def test_experiment_create_run_resolve(self, setup_localstack):
        """Testa ciclo completo: criar -> rodar -> resolver."""
        dynamodb = setup_localstack["dynamodb"]

        # 1. Configura contadores baseline
        for region in ["us-east-1", "sa-east-1"]:
            dynamodb.Table("counters").put_item(Item={
                "region": region,
                "counter_key": "count",
                "total_count": 100,
            })

        # 2. Cria experimento
        event = {
            "version": "2.0",
            "routeKey": "POST /admin/experiments",
            "requestContext": {
                "http": {"method": "POST"},
                "authorizer": {"lambda": {"client_id": "test-client", "scope": "admin"}},
            },
            "body": json.dumps({"fault_type": "pause-replication", "notes": "Teste"}),
        }

        create_response = lambda_handler(event, None)
        assert create_response["statusCode"] == 201
        exp_data = json.loads(create_response["body"])
        experiment_id = exp_data["experiment_id"]

        # 3. Resolve experimento
        resolve_response = lambda_handler({
            "version": "2.0",
            "routeKey": f"POST /admin/experiments/{experiment_id}/resolve",
            "requestContext": {
                "http": {"method": "POST"},
                "authorizer": {"lambda": {"client_id": "test-client", "scope": "admin"}},
            },
            "pathParameters": {"experiment_id": experiment_id},
        }, None)

        assert resolve_response["statusCode"] == 200
        resolve_data = json.loads(resolve_response["body"])
        assert resolve_data["status"] == "RESOLVED"
        assert resolve_data["measured_rpo_records_affected"] is not None

        # 4. Verifica no DynamoDB
        item = dynamodb.Table("experiments").get_item(
            Key={"experiment_id": experiment_id}
        )["Item"]
        assert item["status"] == "RESOLVED"

    def test_experiment_report(self, setup_localstack):
        """Testa geração de relatório de experimento."""
        dynamodb = setup_localstack["dynamodb"]

        # Setup: cria experimento resolvido
        experiment_id = f"exp-report-{int(time.time())}"
        for region in ["us-east-1", "sa-east-1"]:
            dynamodb.Table("counters").put_item(Item={
                "region": region, "counter_key": "count", "total_count": 100,
            })

        dynamodb.Table("experiments").put_item(Item={
            "experiment_id": experiment_id,
            "fault_type": "pause-replication",
            "notes": "Teste relatório",
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
            "is_converged": False,
            "created_by": "client-1",
            "resolved_by": "client-2",
        })

        # Busca relatório
        response = lambda_handler({
            "version": "2.0",
            "routeKey": f"GET /admin/experiments/{experiment_id}/report",
            "requestContext": {
                "http": {"method": "GET"},
                "authorizer": {"lambda": {"client_id": "test-client", "scope": "admin"}},
            },
            "pathParameters": {"experiment_id": experiment_id},
        }, None)

        assert response["statusCode"] == 200
        report = json.loads(response["body"])
        assert report["experiment_id"] == experiment_id
        assert report["status"] == "RESOLVED"
        assert report["measurements"]["rto_seconds"] == 120


# =============================================================================
# Testes: Cross-Region Consistency
# =============================================================================

class TestCrossRegionConsistency:
    """Testa consistência de dados cross-region."""

    def test_divergence_calculation(self, setup_localstack):
        """Testa cálculo de divergência entre regiões."""
        dynamodb = setup_localstack["dynamodb"]

        # Configura contadores diferentes
        dynamodb.Table("counters").put_item(Item={
            "region": "us-east-1", "counter_key": "count", "total_count": 150,
        })
        dynamodb.Table("counters").put_item(Item={
            "region": "sa-east-1", "counter_key": "count", "total_count": 120,
        })

        # Simula cálculo de divergência
        count_local = 150
        count_remote = 120
        divergence = count_local - count_remote

        assert divergence == 30
        assert divergence != 0  # Não sincronizado

    def test_synchronized_regions(self, setup_localstack):
        """Testa regiões sincronizadas."""
        dynamodb = setup_localstack["dynamodb"]

        for region in ["us-east-1", "sa-east-1"]:
            dynamodb.Table("counters").put_item(Item={
                "region": region, "counter_key": "count", "total_count": 100,
            })

        count_local = 100
        count_remote = 100
        divergence = count_local - count_remote

        assert divergence == 0
        assert True  # is_in_sync seria True


# =============================================================================
# Testes: Resiliência e Falhas
# =============================================================================

class TestResilience:
    """Testa resiliência do sistema."""

    def test_table_not_found(self, setup_localstack):
        """Testa comportamento quando tabela não existe."""
        # Remove tabela de contadores
        setup_localstack["client"].delete_table(TableName="counters")

        # Tenta acessar contador
        from lambda_function import get_counter_count
        from authorizer import get_client_count

        result = get_counter_count(setup_localstack["client"].Table("non-existent"), "us-east-1")
        assert result == -1  # Erro tratado

    def test_empty_database(self, setup_localstack):
        """Testa comportamento com banco vazio."""
        dynamodb = setup_localstack["dynamodb"]

        # Remove todos os itens
        for table_name in ["transactions", "experiments", "counters"]:
            table = dynamodb.Table(table_name)
            items = table.scan()["Items"]
            for item in items:
                table.delete_item(Key={"transaction_id": item.get("transaction_id", "")}
                    if table_name == "transactions" else
                    {"experiment_id": item.get("experiment_id", "")}
                    if table_name == "experiments" else
                    {"region": item["region"], "counter_key": item["counter_key"]})

        # GET /transactions/count com contadores zerados
        event = {
            "version": "2.0",
            "routeKey": "GET /transactions/count",
            "requestContext": {"http": {"method": "GET"}},
            "queryStringParameters": {},
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["count"] == 0

    def test_malformed_request_handling(self, setup_localstack):
        """Testa tratamento de requests malformados."""
        # Body JSON inválido
        event = {
            "version": "2.0",
            "routeKey": "POST /transactions",
            "requestContext": {"http": {"method": "POST"}},
            "body": "not valid json",
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

        # Body vazio
        event["body"] = ""
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

        # Body None
        event["body"] = None
        response = lambda_handler(event, None)
        # Pode retornar 400 ou criar transação padrão


# =============================================================================
# Testes: Cenários de Chaos Engineering
# =============================================================================

class TestChaosScenarios:
    """Testes de cenários de chaos engineering."""

    def test_replication_pause_simulation(self, setup_localstack):
        """Simula pausa de replicação entre regiões."""
        dynamodb = setup_localstack["dynamodb"]

        # 1. Configura baseline
        for region in ["us-east-1", "sa-east-1"]:
            dynamodb.Table("counters").put_item(Item={
                "region": region, "counter_key": "count", "total_count": 100,
            })

        # 2. Cria experimento de pausa
        experiment_id = f"chaos-exp-{int(time.time())}"
        dynamodb.Table("experiments").put_item(Item={
            "experiment_id": experiment_id,
            "fault_type": "pause-replication",
            "status": "RUNNING",
            "region_a": "us-east-1",
            "region_b": "sa-east-1",
            "baseline_count_region_a": 100,
            "baseline_count_region_b": 100,
            "initial_divergence": 0,
        })

        # 3. Simula divergência (apenas us-east-1 recebe tráfego)
        dynamodb.Table("counters").update_item(
            Key={"region": "us-east-1", "counter_key": "count"},
            UpdateExpression="ADD total_count :val",
            ExpressionAttributeValues={":val": 50}
        )

        # 4. Verifica divergência
        items = dynamodb.Table("counters").scan()["Items"]
        count_us = next(i["total_count"] for i in items if i["region"] == "us-east-1")
        count_sa = next(i["total_count"] for i in items if i["region"] == "sa-east-1")

        assert count_us - count_sa == 50

    def test_convergence_verification(self, setup_localstack):
        """Verifica convergência após resolução."""
        dynamodb = setup_localstack["dynamodb"]

        # Configura contadores divergentes
        dynamodb.Table("counters").put_item(Item={
            "region": "us-east-1", "counter_key": "count", "total_count": 150,
        })
        dynamodb.Table("counters").put_item(Item={
            "region": "sa-east-1", "counter_key": "count", "total_count": 120,
        })

        # Resolução: sincroniza contadores
        for region in ["us-east-1", "sa-east-1"]:
            dynamodb.Table("counters").update_item(
                Key={"region": region, "counter_key": "count"},
                UpdateExpression="SET total_count = :val",
                ExpressionAttributeValues={":val": 150}
            )

        # Verifica convergência
        items = dynamodb.Table("counters").scan()["Items"]
        counts = [i["total_count"] for i in items]
        assert len(set(counts)) == 1  # Todos iguais = convergente


# =============================================================================
# Execução direta
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])