# =============================================================================
# CloudWatch Dashboard Cross-Region
# =============================================================================
# Dashboard consolidado que mostra métricas de AMBAS as regiões num único
# painel. Inclui:
#   - Replication Latency do DynamoDB Global Table
#   - Lambda Errors, Duration e Invocations de ambas as regiões
#   - API Gateway Request Count e Latency de ambas as regiões
#   - Métricas custom de divergência (TransactionCount por região)
# =============================================================================

locals {
  transactions_table_name = aws_dynamodb_table.transactions.name
  lambda_name_a           = module.region_a.lambda_function_name
  lambda_name_b           = module.region_b.lambda_function_name
  stream_processor_name_a = module.region_a.stream_processor_function_name
  stream_processor_name_b = module.region_b.stream_processor_function_name
  api_gw_id_a             = module.region_a.api_gateway_id
  api_gw_id_b             = module.region_b.api_gateway_id
}

resource "aws_cloudwatch_dashboard" "cross_region" {
  dashboard_name = "${var.project_name}-cross-region-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [

      # ----- Título -----
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 1
        properties = {
          markdown = "# 🔬 ${var.project_name} — Dashboard de Resiliência Multi-Região\n**Primária:** `${var.primary_region}` | **Secundária:** `${var.secondary_region}` | **Ambiente:** `${var.environment}`"
        }
      },

      # ----- DynamoDB Replication Latency -----
      {
        type   = "metric"
        x      = 0
        y      = 1
        width  = 12
        height = 6
        properties = {
          title  = "📡 DynamoDB — Replication Latency (ms)"
          region = var.primary_region
          metrics = [
            ["AWS/DynamoDB", "ReplicationLatency", "TableName", local.transactions_table_name, "ReceivingRegion", var.secondary_region, { region = var.primary_region, label = "${var.primary_region} → ${var.secondary_region}" }],
            ["AWS/DynamoDB", "ReplicationLatency", "TableName", local.transactions_table_name, "ReceivingRegion", var.primary_region, { region = var.secondary_region, label = "${var.secondary_region} → ${var.primary_region}" }]
          ]
          period = 60
          stat   = "Average"
          view   = "timeSeries"
          yAxis = {
            left = {
              min   = 0
              label = "Latência (ms)"
            }
          }
        }
      },

      # ----- DynamoDB Pending Replication Count -----
      {
        type   = "metric"
        x      = 12
        y      = 1
        width  = 12
        height = 6
        properties = {
          title  = "📊 DynamoDB — Pending Replication Count"
          region = var.primary_region
          metrics = [
            ["AWS/DynamoDB", "PendingReplicationCount", "TableName", local.transactions_table_name, { region = var.primary_region, label = var.primary_region }],
            ["AWS/DynamoDB", "PendingReplicationCount", "TableName", local.transactions_table_name, { region = var.secondary_region, label = var.secondary_region }]
          ]
          period = 60
          stat   = "Average"
          view   = "timeSeries"
        }
      },

      # ----- Lambda Errors — Ambas as Regiões -----
      {
        type   = "metric"
        x      = 0
        y      = 7
        width  = 8
        height = 6
        properties = {
          title  = "⚠️ Lambda — Errors"
          region = var.primary_region
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", local.lambda_name_a, { region = var.primary_region, label = "${var.primary_region}", color = "#d62728" }],
            ["AWS/Lambda", "Errors", "FunctionName", local.lambda_name_b, { region = var.secondary_region, label = "${var.secondary_region}", color = "#ff7f0e" }]
          ]
          period = 60
          stat   = "Sum"
          view   = "timeSeries"
        }
      },

      # ----- Lambda Duration — Ambas as Regiões -----
      {
        type   = "metric"
        x      = 8
        y      = 7
        width  = 8
        height = 6
        properties = {
          title  = "⏱️ Lambda — Duration (ms)"
          region = var.primary_region
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", local.lambda_name_a, { region = var.primary_region, label = "${var.primary_region} (avg)", stat = "Average" }],
            ["AWS/Lambda", "Duration", "FunctionName", local.lambda_name_a, { region = var.primary_region, label = "${var.primary_region} (p99)", stat = "p99" }],
            ["AWS/Lambda", "Duration", "FunctionName", local.lambda_name_b, { region = var.secondary_region, label = "${var.secondary_region} (avg)", stat = "Average" }],
            ["AWS/Lambda", "Duration", "FunctionName", local.lambda_name_b, { region = var.secondary_region, label = "${var.secondary_region} (p99)", stat = "p99" }]
          ]
          period = 60
          view   = "timeSeries"
        }
      },

      # ----- Lambda Invocations — Ambas as Regiões -----
      {
        type   = "metric"
        x      = 16
        y      = 7
        width  = 8
        height = 6
        properties = {
          title  = "📈 Lambda — Invocations"
          region = var.primary_region
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", local.lambda_name_a, { region = var.primary_region, label = var.primary_region }],
            ["AWS/Lambda", "Invocations", "FunctionName", local.lambda_name_b, { region = var.secondary_region, label = var.secondary_region }]
          ]
          period = 60
          stat   = "Sum"
          view   = "timeSeries"
        }
      },

      # ----- API Gateway — Request Count -----
      {
        type   = "metric"
        x      = 0
        y      = 13
        width  = 12
        height = 6
        properties = {
          title  = "🌐 API Gateway — Request Count"
          region = var.primary_region
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", local.api_gw_id_a, { region = var.primary_region, label = var.primary_region }],
            ["AWS/ApiGateway", "Count", "ApiId", local.api_gw_id_b, { region = var.secondary_region, label = var.secondary_region }]
          ]
          period = 60
          stat   = "Sum"
          view   = "timeSeries"
        }
      },

      # ----- API Gateway — Latency -----
      {
        type   = "metric"
        x      = 12
        y      = 13
        width  = 12
        height = 6
        properties = {
          title  = "🌐 API Gateway — Latency (ms)"
          region = var.primary_region
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiId", local.api_gw_id_a, { region = var.primary_region, label = "${var.primary_region} (avg)", stat = "Average" }],
            ["AWS/ApiGateway", "Latency", "ApiId", local.api_gw_id_a, { region = var.primary_region, label = "${var.primary_region} (p99)", stat = "p99" }],
            ["AWS/ApiGateway", "Latency", "ApiId", local.api_gw_id_b, { region = var.secondary_region, label = "${var.secondary_region} (avg)", stat = "Average" }],
            ["AWS/ApiGateway", "Latency", "ApiId", local.api_gw_id_b, { region = var.secondary_region, label = "${var.secondary_region} (p99)", stat = "p99" }]
          ]
          period = 60
          view   = "timeSeries"
        }
      },

      # ----- Métricas Custom — Transaction Count por Região -----
      {
        type   = "metric"
        x      = 0
        y      = 19
        width  = 24
        height = 6
        properties = {
          title  = "🔍 Divergência — Transaction Count por Região"
          region = var.primary_region
          metrics = [
            ["${var.project_name}", "TransactionCount", "Region", var.primary_region, { region = var.primary_region, label = "${var.primary_region} — Total Transactions" }],
            ["${var.project_name}", "TransactionCount", "Region", var.secondary_region, { region = var.secondary_region, label = "${var.secondary_region} — Total Transactions" }]
          ]
          period = 60
          stat   = "Maximum"
          view   = "timeSeries"
          annotations = {
            horizontal = []
          }
        }
      },

      # ----- Stream Processor — Errors & Invocations -----
      {
        type   = "metric"
        x      = 0
        y      = 25
        width  = 12
        height = 6
        properties = {
          title  = "🔄 Stream Processor — Errors"
          region = var.primary_region
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", local.stream_processor_name_a, { region = var.primary_region, label = "${var.primary_region}", color = "#d62728" }],
            ["AWS/Lambda", "Errors", "FunctionName", local.stream_processor_name_b, { region = var.secondary_region, label = "${var.secondary_region}", color = "#ff7f0e" }]
          ]
          period = 60
          stat   = "Sum"
          view   = "timeSeries"
        }
      },

      # ----- Stream Processor — Duration & Invocations -----
      {
        type   = "metric"
        x      = 12
        y      = 25
        width  = 12
        height = 6
        properties = {
          title  = "🔄 Stream Processor — Duration & Invocations"
          region = var.primary_region
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", local.stream_processor_name_a, { region = var.primary_region, label = "${var.primary_region} (avg)", stat = "Average" }],
            ["AWS/Lambda", "Duration", "FunctionName", local.stream_processor_name_a, { region = var.primary_region, label = "${var.primary_region} (p99)", stat = "p99" }],
            ["AWS/Lambda", "Duration", "FunctionName", local.stream_processor_name_b, { region = var.secondary_region, label = "${var.secondary_region} (avg)", stat = "Average" }],
            ["AWS/Lambda", "Duration", "FunctionName", local.stream_processor_name_b, { region = var.secondary_region, label = "${var.secondary_region} (p99)", stat = "p99" }],
            ["AWS/Lambda", "Invocations", "FunctionName", local.stream_processor_name_a, { region = var.primary_region, label = "${var.primary_region} Invocations", stat = "Sum" }],
            ["AWS/Lambda", "Invocations", "FunctionName", local.stream_processor_name_b, { region = var.secondary_region, label = "${var.secondary_region} Invocations", stat = "Sum" }],
          ]
          period = 60
          view   = "timeSeries"
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Alarme — Replication Latency Alta
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "replication_latency_high" {
  alarm_name          = "${var.project_name}-replication-lag-high-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ReplicationLatency"
  namespace           = "AWS/DynamoDB"
  period              = 60
  statistic           = "Average"
  threshold           = 30000 # 30 segundos — muito alto, indica problema
  alarm_description   = "Replication latency do DynamoDB Global Table excedeu 30s"

  dimensions = {
    TableName       = local.transactions_table_name
    ReceivingRegion = var.secondary_region
  }

  alarm_actions = []
  ok_actions    = []
}
