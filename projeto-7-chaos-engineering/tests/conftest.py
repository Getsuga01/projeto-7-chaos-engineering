"""
Pytest configuration and shared fixtures for Projeto 7 tests.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock

# Adiciona src ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Configura variáveis de ambiente padrão para testes
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")


@pytest.fixture(autouse=True)
def reset_modules():
    """Reseta módulos entre testes para evitar cache de variáveis de ambiente."""
    # Limpa módulos que podem ter cacheado env vars
    modules_to_clear = [
        "lambda_function",
        "stream_processor",
        "authorizer",
    ]
    for mod in modules_to_clear:
        if mod in sys.modules:
            del sys.modules[mod]
    yield
    for mod in modules_to_clear:
        if mod in sys.modules:
            del sys.modules[mod]


@pytest.fixture
def mock_lambda_context():
    """Mock do contexto Lambda."""
    context = MagicMock()
    context.function_name = "test-function"
    context.function_version = "$LATEST"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    context.memory_limit_in_mb = 256
    context.remaining_time_in_millis = MagicMock(return_value=30000)
    context.aws_request_id = "test-request-id"
    context.log_group_name = "/aws/lambda/test-function"
    context.log_stream_name = "2024/01/01/[$LATEST]test"
    return context


@pytest.fixture
def sample_transaction():
    """Transação de exemplo para testes."""
    return {
        "transaction_id": "test-txn-123",
        "region_written": "us-east-1",
        "amount": 100.50,
        "description": "Test transaction",
        "created_at": "2024-01-01T00:00:00+00:00",
        "created_at_epoch": 1704067200,
        "observed_in_other_region_at": None,
    }


@pytest.fixture
def sample_experiment():
    """Experimento de exemplo para testes."""
    return {
        "experiment_id": "test-exp-123",
        "fault_type": "pause-replication",
        "notes": "Test experiment",
        "started_at": "2024-01-01T00:00:00+00:00",
        "started_at_epoch": 1704067200,
        "fault_resolved_at": None,
        "converged_at": None,
        "measured_rto_seconds": None,
        "measured_rpo_records_affected": None,
        "status": "RUNNING",
        "region_a": "us-east-1",
        "region_b": "sa-east-1",
        "baseline_count_region_a": 100,
        "baseline_count_region_b": 100,
        "initial_divergence": 0,
    }