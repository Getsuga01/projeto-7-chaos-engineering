# =============================================================================
# Valores padrão das variáveis
# =============================================================================
# Ajuste estes valores de acordo com sua conta AWS e preferências.
# ATENÇÃO: Este projeto gera custos reais em sua conta AWS.
# =============================================================================

project_name    = "chaos-lab"
environment     = "sandbox"
primary_region  = "us-east-1"
secondary_region = "sa-east-1"

# Orçamento mensal (USD) — alarme dispara em 80% e 100%
budget_limit = 10

# Email para notificações de orçamento (substitua pelo seu)
budget_notification_email = "seu-email@exemplo.com"

# Duração padrão do experimento FIS (5 minutos)
fis_experiment_duration = "PT5M"
