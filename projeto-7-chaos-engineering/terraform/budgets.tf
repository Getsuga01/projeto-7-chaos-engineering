# =============================================================================
# AWS Budgets — Controle de Custos
# =============================================================================
# Alarmes de orçamento para proteger contra custos inesperados.
# Infraestrutura multi-região gera custo mesmo em repouso (duas réplicas).
# =============================================================================

resource "aws_budgets_budget" "monthly" {
  name         = "${var.project_name}-monthly-budget-${var.environment}"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Filtrar custos apenas pelos recursos deste projeto
  cost_filter {
    name = "TagKeyValue"
    values = [
      "user:Project$${var.project_name}"
    ]
  }

  # Notificação em 80% do orçamento (alerta antecipado)
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = var.budget_notification_email != "" ? [var.budget_notification_email] : []
  }

  # Notificação em 100% do orçamento (limite atingido)
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = var.budget_notification_email != "" ? [var.budget_notification_email] : []
  }

  # Notificação de previsão (forecast) — aviso se a projeção ultrapassar 100%
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_email_addresses = var.budget_notification_email != "" ? [var.budget_notification_email] : []
  }
}
