# =============================================================================
# AWS Fault Injection Service (FIS) — Experiment Template
# =============================================================================
# Template para pausar a replicação do DynamoDB Global Table.
# A ação `aws:dynamodb:global-table-pause-replication` simula uma interrupção
# da replicação entre regiões, permitindo medir RTO e RPO reais.
# =============================================================================

# -----------------------------------------------------------------------------
# IAM Role para o FIS
# -----------------------------------------------------------------------------

resource "aws_iam_role" "fis_role" {
  name = "${var.project_name}-fis-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "fis.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "fis_dynamodb" {
  name = "${var.project_name}-fis-dynamodb-${var.environment}"
  role = aws_iam_role.fis_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "FISDynamoDBActions"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeTable",
          "dynamodb:UpdateTable",
          "dynamodb:DescribeGlobalTable",
          "dynamodb:UpdateGlobalTable",
          "dynamodb:DescribeTableReplicaAutoScaling",
          "dynamodb:DescribeContinuousBackups"
        ]
        Resource = [
          aws_dynamodb_table.transactions.arn,
          "${aws_dynamodb_table.transactions.arn}/*"
        ]
      },
      {
        Sid    = "FISCloudWatchAccess"
        Effect = "Allow"
        Action = [
          "cloudwatch:DescribeAlarms"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Alarm — Stop Condition
# -----------------------------------------------------------------------------
# Este alarme serve como "guarda" de segurança: se a taxa de erros da Lambda
# na região primária ultrapassar o limite, o experimento é encerrado
# automaticamente pelo FIS.
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "lambda_errors_high" {
  alarm_name          = "${var.project_name}-lambda-errors-high-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Alarme de segurança do FIS: encerra experimento se erros da Lambda > 10/min"

  dimensions = {
    FunctionName = module.region_a.lambda_function_name
  }

  # Sem ações — usado apenas como stop condition do FIS
  alarm_actions = []
  ok_actions    = []
}

# -----------------------------------------------------------------------------
# FIS Experiment Template — Pausar Replicação do Global Table
# -----------------------------------------------------------------------------

resource "aws_fis_experiment_template" "pause_replication" {
  description = "Pausa a replicação do DynamoDB Global Table para medir RTO/RPO"
  role_arn    = aws_iam_role.fis_role.arn

  action {
    name        = "PauseReplication"
    action_id   = "aws:dynamodb:global-table-pause-replication"
    description = "Pausa a replicação entre regiões do Global Table de transações"

    target {
      key   = "Tables"
      value = "TransactionsTable"
    }

    parameter {
      key   = "duration"
      value = var.fis_experiment_duration
    }
  }

  target {
    name           = "TransactionsTable"
    resource_type  = "aws:dynamodb:global-table"
    selection_mode = "ALL"

    resource_arns = [
      aws_dynamodb_table.transactions.arn
    ]
  }

  stop_condition {
    source = "aws:cloudwatch:alarm"
    value  = aws_cloudwatch_metric_alarm.lambda_errors_high.arn
  }

  log_configuration {
    cloudwatch_logs_configuration {
      log_group_arn = "${aws_cloudwatch_log_group.fis_logs.arn}:*"
    }
    log_schema_version = 2
  }

  tags = {
    Name      = "${var.project_name}-pause-replication"
    Component = "chaos"
  }
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group para logs do FIS
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "fis_logs" {
  name              = "/aws/fis/${var.project_name}-${var.environment}"
  retention_in_days = 30
}
