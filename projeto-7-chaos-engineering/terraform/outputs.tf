# =============================================================================
# Outputs do projeto
# =============================================================================

output "api_endpoint_region_a" {
  description = "URL do API Gateway na região primária"
  value       = module.region_a.api_endpoint
}

output "api_endpoint_region_b" {
  description = "URL do API Gateway na região secundária"
  value       = module.region_b.api_endpoint
}

output "dynamodb_transactions_table_arn" {
  description = "ARN da tabela DynamoDB de transações (Global Table)"
  value       = aws_dynamodb_table.transactions.arn
}

output "dynamodb_experiments_table_arn" {
  description = "ARN da tabela DynamoDB de experimentos"
  value       = aws_dynamodb_table.experiment_runs.arn
}

output "dynamodb_counters_table_arn" {
  description = "ARN da tabela DynamoDB de contadores materializados"
  value       = aws_dynamodb_table.transaction_counters.arn
}

output "dynamodb_counters_table_name" {
  description = "Nome da tabela DynamoDB de contadores materializados"
  value       = aws_dynamodb_table.transaction_counters.name
}

output "dynamodb_api_clients_table_arn" {
  description = "ARN da tabela DynamoDB de clientes API"
  value       = aws_dynamodb_table.api_clients.arn
}

output "dynamodb_api_clients_table_name" {
  description = "Nome da tabela DynamoDB de clientes API"
  value       = aws_dynamodb_table.api_clients.name
}

output "fis_experiment_template_id" {
  description = "ID do template de experimento FIS"
  value       = aws_fis_experiment_template.pause_replication.id
}

output "cloudwatch_dashboard_url" {
  description = "URL do dashboard CloudWatch cross-region"
  value       = "https://${var.primary_region}.console.aws.amazon.com/cloudwatch/home?region=${var.primary_region}#dashboards:name=${aws_cloudwatch_dashboard.cross_region.dashboard_name}"
}

output "primary_region" {
  description = "Região primária utilizada"
  value       = var.primary_region
}

output "secondary_region" {
  description = "Região secundária utilizada"
  value       = var.secondary_region
}
