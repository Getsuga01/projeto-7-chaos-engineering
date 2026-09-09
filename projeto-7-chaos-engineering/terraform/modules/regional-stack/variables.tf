# =============================================================================
# Variáveis do módulo regional
# =============================================================================

variable "project_name" {
  description = "Nome do projeto"
  type        = string
}

variable "environment" {
  description = "Ambiente (sandbox, dev, staging, prod)"
  type        = string
}

variable "region_name" {
  description = "Nome da região AWS onde este módulo está sendo implantado"
  type        = string
}

variable "dynamodb_table_name" {
  description = "Nome da tabela DynamoDB de transações"
  type        = string
}

variable "dynamodb_table_arn" {
  description = "ARN da tabela DynamoDB de transações"
  type        = string
}

variable "experiments_table_name" {
  description = "Nome da tabela DynamoDB de experimentos"
  type        = string
}

variable "experiments_table_arn" {
  description = "ARN da tabela DynamoDB de experimentos"
  type        = string
}

variable "counters_table_name" {
  description = "Nome da tabela DynamoDB de contadores materializados"
  type        = string
}

variable "counters_table_arn" {
  description = "ARN da tabela DynamoDB de contadores materializados"
  type        = string
}

variable "transactions_stream_arn" {
  description = "ARN do Stream da tabela de transações (para Lambda stream processor)"
  type        = string
}

variable "api_clients_table_name" {
  description = "Nome da tabela DynamoDB de clientes API"
  type        = string
}

variable "api_clients_table_arn" {
  description = "ARN da tabela DynamoDB de clientes API"
  type        = string
}

variable "lambda_zip_path" {
  description = "Caminho para o arquivo ZIP da Lambda API"
  type        = string
}

variable "lambda_zip_hash" {
  description = "Hash SHA256 do ZIP da Lambda API (para detectar mudanças)"
  type        = string
}

variable "authorizer_zip_path" {
  description = "Caminho para o arquivo ZIP do Authorizer"
  type        = string
}

variable "authorizer_zip_hash" {
  description = "Hash SHA256 do ZIP do Authorizer (para detectar mudanças)"
  type        = string
}

variable "jwt_secret" {
  description = "Secret para assinatura JWT (em produção, use Secrets Manager)"
  type        = string
  sensitive   = true
}

variable "token_ttl_seconds" {
  description = "TTL do token JWT em segundos"
  type        = number
  default     = 3600
}

variable "other_region" {
  description = "Nome da outra região (para referência cross-region na Lambda)"
  type        = string
}
