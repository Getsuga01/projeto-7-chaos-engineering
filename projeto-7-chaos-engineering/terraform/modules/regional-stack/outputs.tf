# =============================================================================
# Outputs do módulo regional
# =============================================================================

output "api_endpoint" {
  description = "URL do API Gateway HTTP API"
  value       = aws_apigatewayv2_api.http_api.api_endpoint
}

output "lambda_function_arn" {
  description = "ARN da Lambda function (API)"
  value       = aws_lambda_function.api.arn
}

output "lambda_function_name" {
  description = "Nome da Lambda function (API)"
  value       = aws_lambda_function.api.function_name
}

output "stream_processor_function_arn" {
  description = "ARN da Lambda Stream Processor"
  value       = aws_lambda_function.stream_processor.arn
}

output "stream_processor_function_name" {
  description = "Nome da Lambda Stream Processor"
  value       = aws_lambda_function.stream_processor.function_name
}

output "lambda_log_group_name" {
  description = "Nome do CloudWatch Log Group da Lambda API"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

output "stream_processor_log_group_name" {
  description = "Nome do CloudWatch Log Group do Stream Processor"
  value       = aws_cloudwatch_log_group.stream_processor_logs.name
}

output "api_gateway_id" {
  description = "ID do API Gateway"
  value       = aws_apigatewayv2_api.http_api.id
}

output "api_gateway_execution_arn" {
  description = "Execution ARN do API Gateway"
  value       = aws_apigatewayv2_api.http_api.execution_arn
}
