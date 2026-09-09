# =============================================================================
# Variáveis globais do projeto
# =============================================================================

variable "project_name" {
  description = "Nome do projeto — usado como prefixo em todos os recursos"
  type        = string
  default     = "chaos-lab"
}

variable "environment" {
  description = "Ambiente de deploy (sandbox, dev, staging, prod)"
  type        = string
  default     = "sandbox"

  validation {
    condition     = contains(["sandbox", "dev", "staging", "prod"], var.environment)
    error_message = "Environment deve ser sandbox, dev, staging ou prod."
  }
}

variable "primary_region" {
  description = "Região AWS primária"
  type        = string
  default     = "us-east-1"
}

variable "secondary_region" {
  description = "Região AWS secundária (réplica)"
  type        = string
  default     = "sa-east-1"
}

variable "budget_limit" {
  description = "Limite mensal de orçamento em USD"
  type        = number
  default     = 10
}

variable "budget_notification_email" {
  description = "Email para notificações de orçamento"
  type        = string
  default     = ""
}

variable "fis_experiment_duration" {
  description = "Duração padrão do experimento FIS (formato ISO 8601)"
  type        = string
  default     = "PT5M"
}

variable "jwt_secret" {
  description = "Secret para assinatura JWT (em produção, use AWS Secrets Manager)"
  type        = string
  sensitive   = true
  default     = "dev-secret-change-in-production"
}

variable "token_ttl_seconds" {
  description = "TTL do token JWT em segundos"
  type        = number
  default     = 3600
}
