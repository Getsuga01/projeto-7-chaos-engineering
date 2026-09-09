"""
Projeto 7 — Lambda Authorizer (JWT/HMAC)
=========================================

Autenticação simples para endpoints /admin/* usando JWT assinado com HMAC.
Para produção, substitua por Cognito, Auth0, ou similar.

Fluxo:
1. Cliente obtém token via POST /auth/token (client_id + client_secret)
2. Cliente envia token no header Authorization: Bearer <token>
3. Authorizer valida assinatura, expiração e escopo (admin)
4. Retorna policy IAM permitindo/negando acesso
"""

import json
import os
import time
import hmac
import hashlib
import base64
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Em produção, use Secrets Manager ou Parameter Store
# Para sandbox, variável de ambiente (configure via Terraform)
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = int(os.environ.get("TOKEN_TTL_SECONDS", "3600"))  # 1 hora

# Clientes para validação de client credentials
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("REGION_NAME", "us-east-1"))
CLIENTS_TABLE = os.environ.get("CLIENTS_TABLE", "chaos-lab-api-clients")
clients_table = dynamodb.Table(CLIENTS_TABLE)


# ---------------------------------------------------------------------------
# Helpers JWT
# ---------------------------------------------------------------------------

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(client_id: str, scope: str = "admin") -> str:
    """Cria JWT simples com HMAC-SHA256."""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": client_id,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "scope": scope,
    }

    header_b64 = base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = base64url_encode(json.dumps(payload, separators=(",", ":")).encode())

    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    signature_b64 = base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_token(token: str) -> dict | None:
    """Verifica e decodifica JWT. Retorna payload se válido, None caso contrário."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode()

        # Verifica assinatura
        expected_sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(base64url_decode(signature_b64), expected_sig):
            logger.warning("Assinatura JWT inválida")
            return None

        # Decodifica payload
        payload = json.loads(base64url_decode(payload_b64))

        # Verifica expiração
        if payload.get("exp", 0) < int(time.time()):
            logger.warning("Token expirado")
            return None

        return payload

    except Exception as e:
        logger.warning(f"Erro ao verificar token: {e}")
        return None


def generate_policy(principal_id: str, effect: str, resource: str, context: dict = None) -> dict:
    """Gera policy IAM para API Gateway."""
    policy = {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resource,
                }
            ],
        },
    }
    if context:
        policy["context"] = context
    return policy


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_authorize(event: dict) -> dict:
    """
    Lambda Authorizer — valida token no header Authorization.
    Evento: type=TOKEN (REST API) ou type=REQUEST (HTTP API)
    """
    logger.info(f"Authorizer event: {json.dumps(event, default=str)}")

    # HTTP API (payload v2.0) — token no header Authorization
    auth_header = None
    if event.get("type") == "REQUEST":
        headers = event.get("headers", {}) or {}
        auth_header = headers.get("authorization") or headers.get("Authorization")
    elif event.get("type") == "TOKEN":
        auth_header = event.get("authorizationToken")

    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Header Authorization ausente ou malformado")
        return generate_policy("anonymous", "Deny", event.get("routeArn", "*"))

    token = auth_header[7:]  # Remove "Bearer "
    payload = verify_token(token)

    if not payload:
        logger.warning("Token inválido ou expirado")
        return generate_policy("anonymous", "Deny", event.get("routeArn", "*"))

    # Verifica escopo admin
    if payload.get("scope") != "admin":
        logger.warning(f"Escopo insuficiente: {payload.get('scope')}")
        return generate_policy(payload.get("sub", "unknown"), "Deny", event.get("routeArn", "*"))

    # Verifica se client existe e está ativo
    client_id = payload.get("sub")
    try:
        resp = clients_table.get_item(Key={"client_id": client_id})
        if "Item" not in resp or not resp["Item"].get("active", True):
            logger.warning(f"Client {client_id} não encontrado ou inativo")
            return generate_policy(client_id, "Deny", event.get("routeArn", "*"))
    except ClientError as e:
        logger.error(f"Erro ao validar client: {e}")
        return generate_policy(client_id, "Deny", event.get("routeArn", "*"))

    # Permite acesso — injeta client_id no context para uso downstream
    logger.info(f"Autorizado: {client_id}")
    return generate_policy(
        client_id,
        "Allow",
        event.get("routeArn", "*"),
        context={"client_id": client_id, "scope": payload.get("scope")},
    )


def handle_token(event: dict) -> dict:
    """
    POST /auth/token — Emite token JWT para client_id + client_secret válidos.
    Body: { "client_id": "...", "client_secret": "...", "scope": "admin" }
    """
    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"error": "JSON inválido"})}

    client_id = body.get("client_id")
    client_secret = body.get("client_secret")
    scope = body.get("scope", "admin")

    if not client_id or not client_secret:
        return {"statusCode": 400, "body": json.dumps({"error": "client_id e client_secret obrigatórios"})}

    try:
        resp = clients_table.get_item(Key={"client_id": client_id})
        if "Item" not in resp:
            return {"statusCode": 401, "body": json.dumps({"error": "Credenciais inválidas"})}

        client = resp["Item"]
        # Verifica secret (em produção, use hash bcrypt/argon2)
        if client.get("client_secret") != client_secret:
            return {"statusCode": 401, "body": json.dumps({"error": "Credenciais inválidas"})}

        if not client.get("active", True):
            return {"statusCode": 403, "body": json.dumps({"error": "Client desativado"})}

        if scope not in client.get("allowed_scopes", ["admin"]):
            return {"statusCode": 403, "body": json.dumps({"error": "Escopo não permitido para este client"})}

        token = create_token(client_id, scope)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": TOKEN_TTL_SECONDS,
                "scope": scope,
            }),
        }

    except ClientError as e:
        logger.error(f"Erro ao emitir token: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Erro interno"})}


def lambda_handler(event: dict, context) -> dict:
    """Router do Authorizer."""
    route_key = event.get("routeKey", "")
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")

    # POST /auth/token — emissão de token (público)
    if route_key == "POST /auth/token" or (http_method == "POST" and event.get("rawPath") == "/auth/token"):
        return handle_token(event)

    # Authorizer — validação de token (protegido)
    return handle_authorize(event)