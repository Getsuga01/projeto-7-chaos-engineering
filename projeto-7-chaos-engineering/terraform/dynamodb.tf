# -----------------------------------------------------------------------------
# Tabela: api_clients (Clientes para autenticação JWT)
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "api_clients" {
  name         = "${var.project_name}-api-clients-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "client_id"

  attribute {
    name = "client_id"
    type = "S"
  }

  # TTL para limpeza automática de clients expirados
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = {
    Component = "auth"
    Table     = "api_clients"
  }
}

resource "aws_dynamodb_table" "transactions" {
  name         = "${var.project_name}-transactions-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "transaction_id"

  # Streams habilitados — obrigatório para Global Tables
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "transaction_id"
    type = "S"
  }

  # Réplica na região secundária
  replica {
    region_name = var.secondary_region
  }

  # Proteção contra destruição acidental
  lifecycle {
    prevent_destroy = false # sandbox — mude para true em produção
  }

  tags = {
    Component = "data"
    Table     = "transactions"
  }
}

# -----------------------------------------------------------------------------
# Tabela: experiment_runs
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "experiment_runs" {
  name         = "${var.project_name}-experiments-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "experiment_id"

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "experiment_id"
    type = "S"
  }

  replica {
    region_name = var.secondary_region
  }

  lifecycle {
    prevent_destroy = false
  }

  tags = {
    Component = "data"
    Table     = "experiment_runs"
  }
}

# -----------------------------------------------------------------------------
# Tabela: transaction_counters (Contador Materializado por Região)
# -----------------------------------------------------------------------------
# Evita Scan O(N) na tabela de transações. Atualizada via DynamoDB Stream
# (Lambda stream processor) a cada insert/delete.
# PK: region (S), SK: "count" (S) — item único por região.
# =============================================================================

resource "aws_dynamodb_table" "transaction_counters" {
  name         = "${var.project_name}-txn-counters-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "region"
  range_key    = "counter_key"

  attribute {
    name = "region"
    type = "S"
  }

  attribute {
    name = "counter_key"
    type = "S"
  }

  # Réplica na região secundária para leitura cross-region rápida
  replica {
    region_name = var.secondary_region
  }

  lifecycle {
    prevent_destroy = false
  }

  tags = {
    Component = "data"
    Table     = "transaction_counters"
  }
}
