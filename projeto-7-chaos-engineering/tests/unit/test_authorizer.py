"""
Testes unitários para o Authorizer (authorizer.py).
"""
import json
import os
import sys
import time
from unittest.mock import patch, MagicMock

import pytest
import boto3
from moto import mock_aws

# Adiciona src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Configura variáveis de ambiente ANTES de importar
os.environ["JWT_SECRET"] = "test-secret-key"
os.environ["CLIENTS_TABLE"] = "test-api-clients"
os.environ["REGION_NAME"] = "us-east-1"
os.environ["TOKEN_TTL_SECONDS"] = "3600"

from authorizer import (
    lambda_handler,
    handle_authorize,
    handle_token,
    create_token,
    verify_token,
    generate_policy,
    base64url_encode,
    base64url_decode,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def setup_clients_table():
    """Cria tabela de clientes mockada."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-api-clients",
            KeySchema=[{"AttributeName": "client_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "client_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # Insere cliente de teste
        table.put_item(Item={
            "client_id": "test-client",
            "client_secret": "test-secret",
            "active": True,
            "allowed_scopes": ["admin", "read"],
            "created_at": "2024-01-01T00:00:00+00:00",
        })
        yield table


@pytest.fixture
def valid_token(setup_clients_table):
    """Gera token válido para testes."""
    return create_token("test-client", "admin")


@pytest.fixture
def expired_token():
    """Gera token expirado."""
    # Cria token com expiração no passado
    import hmac
    import hashlib
    import base64

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": "test-client",
        "iat": int(time.time()) - 7200,  # 2 horas atrás
        "exp": int(time.time()) - 3600,  # 1 hora atrás (expirado)
        "scope": "admin",
    }

    header_b64 = base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = base64url_encode(json.dumps(payload, separators=(",", ":")).encode())

    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new("test-secret-key".encode(), signing_input, hashlib.sha256).digest()
    signature_b64 = base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


# =============================================================================
# Testes: base64url_encode/decode
# =============================================================================

class TestBase64URL:
    """Testes para encoding/decoding base64url."""

    def test_encode_decode_roundtrip(self):
        """Testa roundtrip encode/decode."""
        data = b"hello world"
        encoded = base64url_encode(data)
        decoded = base64url_decode(encoded)
        assert decoded == data

    def test_encode_no_padding(self):
        """Testa que encoding remove padding."""
        data = b"test"
        encoded = base64url_encode(data)
        assert "=" not in encoded

    def test_decode_handles_padding(self):
        """Testa que decode lida com padding ausente."""
        encoded = "dGVzdA"  # "test" sem padding
        decoded = base64url_decode(encoded)
        assert decoded == b"test"


# =============================================================================
# Testes: create_token / verify_token
# =============================================================================

class TestJWT:
    """Testes para criação e verificação de JWT."""

    def test_create_token_structure(self):
        """Testa estrutura do token criado."""
        token = create_token("test-client", "admin")
        parts = token.split(".")
        assert len(parts) == 3

        # Decodifica header
        header = json.loads(base64url_decode(parts[0]))
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"

        # Decodifica payload
        payload = json.loads(base64url_decode(parts[1]))
        assert payload["sub"] == "test-client"
        assert payload["scope"] == "admin"
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] - payload["iat"] == 3600  # TTL padrão

    def test_verify_valid_token(self, valid_token):
        """Testa verificação de token válido."""
        payload = verify_token(valid_token)
        assert payload is not None
        assert payload["sub"] == "test-client"
        assert payload["scope"] == "admin"

    def test_verify_expired_token(self, expired_token):
        """Testa verificação de token expirado."""
        payload = verify_token(expired_token)
        assert payload is None

    def test_verify_invalid_signature(self):
        """Testa verificação com assinatura inválida."""
        # Token válido mas com secret diferente
        token = create_token("test-client", "admin")
        parts = token.split(".")
        # Corrompe assinatura
        bad_token = f"{parts[0]}.{parts[1]}.invalid_signature"
        payload = verify_token(bad_token)
        assert payload is None

    def test_verify_malformed_token(self):
        """Testa verificação de token malformado."""
        payload = verify_token("invalid.token")
        assert payload is None

        payload = verify_token("a.b.c.d")  # Muitas partes
        assert payload is None

    def test_token_with_different_scope(self):
        """Testa token com escopo diferente."""
        token = create_token("test-client", "read")
        payload = verify_token(token)
        assert payload["scope"] == "read"


# =============================================================================
# Testes: generate_policy
# =============================================================================

class TestGeneratePolicy:
    """Testes para geração de policy IAM."""

    def test_allow_policy(self):
        """Testa policy de permissão."""
        policy = generate_policy("user123", "Allow", "arn:aws:execute-api:*:*:*")
        assert policy["principalId"] == "user123"
        assert policy["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert policy["policyDocument"]["Statement"][0]["Resource"] == "arn:aws:execute-api:*:*:*"

    def test_deny_policy(self):
        """Testa policy de negação."""
        policy = generate_policy("user123", "Deny", "arn:aws:execute-api:*:*:*")
        assert policy["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_policy_with_context(self):
        """Testa policy com context."""
        policy = generate_policy("user123", "Allow", "*", {"client_id": "test", "scope": "admin"})
        assert policy["context"]["client_id"] == "test"
        assert policy["context"]["scope"] == "admin"


# =============================================================================
# Testes: handle_token (POST /auth/token)
# =============================================================================

class TestHandleToken:
    """Testes para emissão de token."""

    def test_token_success(self, setup_clients_table):
        """Testa emissão de token bem-sucedida."""
        event = {
            "body": json.dumps({
                "client_id": "test-client",
                "client_secret": "test-secret",
                "scope": "admin"
            })
        }
        response = handle_token(event)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "access_token" in body
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 3600
        assert body["scope"] == "admin"

        # Verifica se token é válido
        payload = verify_token(body["access_token"])
        assert payload["sub"] == "test-client"

    def test_token_missing_credentials(self, setup_clients_table):
        """Testa erro com credenciais ausentes."""
        event = {"body": json.dumps({"client_id": "test-client"})}
        response = handle_token(event)
        assert response["statusCode"] == 400

        event = {"body": json.dumps({})}
        response = handle_token(event)
        assert response["statusCode"] == 400

    def test_token_invalid_client(self, setup_clients_table):
        """Testa erro com client inexistente."""
        event = {"body": json.dumps({
            "client_id": "non-existent",
            "client_secret": "secret"
        })}
        response = handle_token(event)
        assert response["statusCode"] == 401

    def test_token_wrong_secret(self, setup_clients_table):
        """Testa erro com secret incorreto."""
        event = {"body": json.dumps({
            "client_id": "test-client",
            "client_secret": "wrong-secret"
        })}
        response = handle_token(event)
        assert response["statusCode"] == 401

    def test_token_inactive_client(self, setup_clients_table):
        """Testa erro com client inativo."""
        setup_clients_table.update_item(
            Key={"client_id": "test-client"},
            UpdateExpression="SET active = :val",
            ExpressionAttributeValues={":val": False}
        )

        event = {"body": json.dumps({
            "client_id": "test-client",
            "client_secret": "test-secret"
        })}
        response = handle_token(event)
        assert response["statusCode"] == 403

    def test_token_scope_not_allowed(self, setup_clients_table):
        """Testa erro com escopo não permitido."""
        event = {"body": json.dumps({
            "client_id": "test-client",
            "client_secret": "test-secret",
            "scope": "write"  # Não está em allowed_scopes
        })}
        response = handle_token(event)
        assert response["statusCode"] == 403

    def test_token_default_scope(self, setup_clients_table):
        """Testa escopo padrão (admin)."""
        event = {"body": json.dumps({
            "client_id": "test-client",
            "client_secret": "test-secret"
        })}
        response = handle_token(event)
        body = json.loads(response["body"])
        assert body["scope"] == "admin"


# =============================================================================
# Testes: handle_authorize (Authorizer)
# =============================================================================

class TestHandleAuthorize:
    """Testes para autorização de requests."""

    def make_authorize_event(self, token=None, route_arn="arn:aws:execute-api:us-east-1:123456789012:test/*/*/*"):
        """Helper para criar evento de autorização."""
        headers = {}
        if token:
            headers["authorization"] = f"Bearer {token}"

        return {
            "version": "2.0",
            "type": "REQUEST",
            "routeArn": route_arn,
            "headers": headers,
            "requestContext": {
                "http": {"method": "POST", "path": "/admin/experiments"},
            },
        }

    def test_authorize_valid_token(self, setup_clients_table, valid_token):
        """Testa autorização com token válido."""
        event = self.make_authorize_event(valid_token)
        response = handle_authorize(event)

        assert response["principalId"] == "test-client"
        assert response["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert response["context"]["client_id"] == "test-client"
        assert response["context"]["scope"] == "admin"

    def test_authorize_missing_token(self, setup_clients_table):
        """Testa autorização sem token."""
        event = self.make_authorize_event(None)
        response = handle_authorize(event)

        assert response["principalId"] == "anonymous"
        assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_authorize_invalid_token_format(self, setup_clients_table):
        """Testa autorização com formato inválido."""
        event = self.make_authorize_event("invalid-token")
        response = handle_authorize(event)

        assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_authorize_expired_token(self, setup_clients_table, expired_token):
        """Testa autorização com token expirado."""
        event = self.make_authorize_event(expired_token)
        response = handle_authorize(event)

        assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_authorize_wrong_scope(self, setup_clients_table):
        """Testa autorização com escopo incorreto."""
        token = create_token("test-client", "read")  # scope read, não admin
        event = self.make_authorize_event(token)
        response = handle_authorize(event)

        assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_authorize_inactive_client(self, setup_clients_table, valid_token):
        """Testa autorização com client inativo."""
        setup_clients_table.update_item(
            Key={"client_id": "test-client"},
            UpdateExpression="SET active = :val",
            ExpressionAttributeValues={":val": False}
        )

        event = self.make_authorize_event(valid_token)
        response = handle_authorize(event)

        assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_authorize_token_type_request(self, setup_clients_table, valid_token):
        """Testa autorização com type=REQUEST (HTTP API)."""
        event = {
            "version": "2.0",
            "type": "REQUEST",
            "routeArn": "arn:aws:execute-api:us-east-1:123456789012:test/*/*/*",
            "headers": {"authorization": f"Bearer {valid_token}"},
            "requestContext": {"http": {"method": "POST"}},
        }
        response = handle_authorize(event)
        assert response["policyDocument"]["Statement"][0]["Effect"] == "Allow"


# =============================================================================
# Testes: lambda_handler (Router)
# =============================================================================

class TestAuthorizerLambdaHandler:
    """Testes para o router do Authorizer."""

    def test_route_token_endpoint(self, setup_clients_table):
        """Testa roteamento para POST /auth/token."""
        event = {
            "routeKey": "POST /auth/token",
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/auth/token",
            "body": json.dumps({
                "client_id": "test-client",
                "client_secret": "test-secret"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 200

    def test_route_authorize(self, setup_clients_table):
        """Testa roteamento para authorizer."""
        token = create_token("test-client", "admin")
        event = {
            "type": "REQUEST",
            "routeArn": "arn:aws:execute-api:us-east-1:123456789012:test/*/*/*",
            "headers": {"authorization": f"Bearer {token}"},
            "requestContext": {"http": {"method": "POST"}},
        }
        response = lambda_handler(event, None)
        assert response["policyDocument"]["Statement"][0]["Effect"] == "Allow"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])