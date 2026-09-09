# =============================================================================
# Módulo Regional — Lambda + API Gateway HTTP API + IAM
# =============================================================================
# Este módulo é instanciado uma vez por região.
# Cada instância recebe o provider da sua região via meta-argumento.
# Inclui:
#   - Lambda API (handler principal)
#   - Lambda Stream Processor (atualiza contadores materializados)
#   - Lambda Authorizer (JWT/HMAC para endpoints /admin/*)
#   - API Gateway HTTP API v2
#   - IAM Roles e Policies
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# Lambda Deployment Packages
# -----------------------------------------------------------------------------

data "archive_file" "stream_processor_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../src/stream_processor"
  output_path = "${path.module}/../../dist/stream_processor.zip"
}

# -----------------------------------------------------------------------------
# IAM — Role da Lambda API
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-${var.region_name}-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "${var.project_name}-lambda-dynamodb-${var.region_name}"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:DescribeTable"
        ]
        Resource = [
          var.dynamodb_table_arn,
          "${var.dynamodb_table_arn}/index/*",
          var.experiments_table_arn,
          "${var.experiments_table_arn}/index/*",
          var.counters_table_arn,
          "${var.counters_table_arn}/index/*"
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Sid    = "CloudWatchMetrics"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# IAM — Role do Stream Processor
# -----------------------------------------------------------------------------

resource "aws_iam_role" "stream_processor_role" {
  name = "${var.project_name}-stream-processor-${var.region_name}-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "stream_processor_dynamodb" {
  name = "${var.project_name}-stream-processor-dynamodb-${var.region_name}"
  role = aws_iam_role.stream_processor_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBStreamRead"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams"
        ]
        Resource = [
          var.transactions_stream_arn
        ]
      },
      {
        Sid    = "CountersTableWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:UpdateItem",
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ]
        Resource = [
          var.counters_table_arn
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# IAM — Role do Authorizer
# -----------------------------------------------------------------------------

resource "aws_iam_role" "authorizer_role" {
  name = "${var.project_name}-authorizer-${var.region_name}-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "authorizer_dynamodb" {
  name = "${var.project_name}-authorizer-dynamodb-${var.region_name}"
  role = aws_iam_role.authorizer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ApiClientsTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = [
          var.api_clients_table_arn,
          "${var.api_clients_table_arn}/index/*"
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Log Groups
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.project_name}-api-${var.region_name}-${var.environment}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "stream_processor_logs" {
  name              = "/aws/lambda/${var.project_name}-stream-processor-${var.region_name}-${var.environment}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "authorizer_logs" {
  name              = "/aws/lambda/${var.project_name}-authorizer-${var.region_name}-${var.environment}"
  retention_in_days = 14
}

# -----------------------------------------------------------------------------
# Lambda Function — API Principal
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "api" {
  function_name    = "${var.project_name}-api-${var.region_name}-${var.environment}"
  filename         = var.lambda_zip_path
  source_code_hash = var.lambda_zip_hash
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256

  role = aws_iam_role.lambda_role.arn

  environment {
    variables = {
      TRANSACTIONS_TABLE   = var.dynamodb_table_name
      EXPERIMENTS_TABLE    = var.experiments_table_name
      COUNTERS_TABLE       = var.counters_table_name
      REGION_NAME          = var.region_name
      OTHER_REGION         = var.other_region
      ENVIRONMENT          = var.environment
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_logs,
    aws_iam_role_policy.lambda_dynamodb
  ]
}

# -----------------------------------------------------------------------------
# Lambda Function — Stream Processor (Contadores Materializados)
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "stream_processor" {
  function_name    = "${var.project_name}-stream-processor-${var.region_name}-${var.environment}"
  filename         = data.archive_file.stream_processor_zip.output_path
  source_code_hash = data.archive_file.stream_processor_zip.output_base64sha256
  handler          = "stream_processor.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256

  role = aws_iam_role.stream_processor_role.arn

  environment {
    variables = {
      COUNTERS_TABLE = var.counters_table_name
      REGION_NAME    = var.region_name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.stream_processor_logs,
    aws_iam_role_policy.stream_processor_dynamodb
  ]
}

# -----------------------------------------------------------------------------
# Lambda Function — Authorizer (JWT/HMAC)
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "authorizer" {
  function_name    = "${var.project_name}-authorizer-${var.region_name}-${var.environment}"
  filename         = var.authorizer_zip_path
  source_code_hash = var.authorizer_zip_hash
  handler          = "authorizer.lambda_handler"
  runtime          = "python3.12"
  timeout          = 10
  memory_size      = 128

  role = aws_iam_role.authorizer_role.arn

  environment {
    variables = {
      CLIENTS_TABLE      = var.api_clients_table_name
      REGION_NAME        = var.region_name
      JWT_SECRET         = var.jwt_secret
      TOKEN_TTL_SECONDS  = var.token_ttl_seconds
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.authorizer_logs,
    aws_iam_role_policy.authorizer_dynamodb
  ]
}

# -----------------------------------------------------------------------------
# Event Source Mapping — Stream Processor → Transactions Stream
# -----------------------------------------------------------------------------

resource "aws_lambda_event_source_mapping" "stream_processor" {
  event_source_arn = var.transactions_stream_arn
  function_name    = aws_lambda_function.stream_processor.arn
  starting_position = "LATEST"
  batch_size       = 100
  maximum_batching_window_in_seconds = 5
  parallelization_factor = 2
}

# -----------------------------------------------------------------------------
# API Gateway HTTP API (v2)
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "http_api" {
  name          = "${var.project_name}-api-${var.region_name}-${var.environment}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 300
  }
}

# -----------------------------------------------------------------------------
# API Gateway Authorizer (Lambda Request Authorizer)
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_authorizer" "jwt_authorizer" {
  api_id               = aws_apigatewayv2_api.http_api.id
  authorizer_type      = "REQUEST"
  authorizer_uri       = aws_lambda_function.authorizer.invoke_arn
  authorizer_payload_version = "2.0"
  enable_simple_responses = true
  identity_sources     = ["$request.header.Authorization"]
  name                 = "${var.project_name}-jwt-authorizer-${var.region_name}"
}

resource "aws_lambda_permission" "authorizer_invoke" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gw_logs.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_cloudwatch_log_group" "api_gw_logs" {
  name              = "/aws/apigateway/${var.project_name}-${var.region_name}-${var.environment}"
  retention_in_days = 14
}

# -----------------------------------------------------------------------------
# Lambda Integration
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "authorizer_token_integration" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.authorizer.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# -----------------------------------------------------------------------------
# Rotas da API — Públicas (sem authorizer)
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_route" "post_transactions" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /transactions"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_route" "get_transactions_count" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /transactions/count"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_route" "post_auth_token" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /auth/token"
  target    = "integrations/${aws_apigatewayv2_integration.authorizer_token_integration.id}"
}

# Health check endpoint
resource "aws_apigatewayv2_route" "get_health" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

# -----------------------------------------------------------------------------
# Rotas da API — Protegidas (com JWT Authorizer)
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_route" "post_experiments" {
  api_id           = aws_apigatewayv2_api.http_api.id
  route_key        = "POST /admin/experiments"
  target           = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorizer_id    = aws_apigatewayv2_authorizer.jwt_authorizer.id
  authorization_type = "CUSTOM"
}

resource "aws_apigatewayv2_route" "post_experiment_resolve" {
  api_id           = aws_apigatewayv2_api.http_api.id
  route_key        = "POST /admin/experiments/{id}/resolve"
  target           = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorizer_id    = aws_apigatewayv2_authorizer.jwt_authorizer.id
  authorization_type = "CUSTOM"
}

resource "aws_apigatewayv2_route" "get_experiment_report" {
  api_id           = aws_apigatewayv2_api.http_api.id
  route_key        = "GET /admin/experiments/{id}/report"
  target           = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
  authorizer_id    = aws_apigatewayv2_authorizer.jwt_authorizer.id
  authorization_type = "CUSTOM"
}

# -----------------------------------------------------------------------------
# Permissão para API Gateway invocar a Lambda API
# -----------------------------------------------------------------------------

resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}
