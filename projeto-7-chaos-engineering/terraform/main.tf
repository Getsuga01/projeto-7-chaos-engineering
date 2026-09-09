# =============================================================================
# Projeto 7 — Laboratório de Resiliência Multi-Região com Chaos Engineering
# =============================================================================
# Root Terraform configuration — multi-region providers + module orchestration
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

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

# -----------------------------------------------------------------------------
# Providers — um por região
# -----------------------------------------------------------------------------

provider "aws" {
  region = var.primary_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

provider "aws" {
  alias  = "secondary"
  region = var.secondary_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# -----------------------------------------------------------------------------
# Data sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_region" "primary" {}

data "aws_region" "secondary" {
  provider = aws.secondary
}

# -----------------------------------------------------------------------------
# Lambda deployment packages
# -----------------------------------------------------------------------------

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/lambda"
  output_path = "${path.module}/../dist/lambda.zip"
}

data "archive_file" "authorizer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/authorizer"
  output_path = "${path.module}/../dist/authorizer.zip"
}

# -----------------------------------------------------------------------------
# Módulo regional — Região Primária (us-east-1)
# -----------------------------------------------------------------------------

module "region_a" {
  source = "./modules/regional-stack"

  providers = {
    aws = aws
  }

  project_name               = var.project_name
  environment                = var.environment
  region_name                = var.primary_region
  dynamodb_table_name        = aws_dynamodb_table.transactions.name
  dynamodb_table_arn         = aws_dynamodb_table.transactions.arn
  experiments_table_name     = aws_dynamodb_table.experiment_runs.name
  experiments_table_arn      = aws_dynamodb_table.experiment_runs.arn
  counters_table_name        = aws_dynamodb_table.transaction_counters.name
  counters_table_arn         = aws_dynamodb_table.transaction_counters.arn
  api_clients_table_name     = aws_dynamodb_table.api_clients.name
  api_clients_table_arn      = aws_dynamodb_table.api_clients.arn
  transactions_stream_arn    = aws_dynamodb_table.transactions.stream_arn
  lambda_zip_path            = data.archive_file.lambda_zip.output_path
  lambda_zip_hash            = data.archive_file.lambda_zip.output_base64sha256
  authorizer_zip_path        = data.archive_file.authorizer_zip.output_path
  authorizer_zip_hash        = data.archive_file.authorizer_zip.output_base64sha256
  jwt_secret                 = var.jwt_secret
  token_ttl_seconds          = var.token_ttl_seconds
  other_region               = var.secondary_region
}

# -----------------------------------------------------------------------------
# Módulo regional — Região Secundária (sa-east-1)
# -----------------------------------------------------------------------------

module "region_b" {
  source = "./modules/regional-stack"

  providers = {
    aws = aws.secondary
  }

  project_name               = var.project_name
  environment                = var.environment
  region_name                = var.secondary_region
  dynamodb_table_name        = aws_dynamodb_table.transactions.name
  dynamodb_table_arn         = aws_dynamodb_table.transactions.arn
  experiments_table_name     = aws_dynamodb_table.experiment_runs.name
  experiments_table_arn      = aws_dynamodb_table.experiment_runs.arn
  counters_table_name        = aws_dynamodb_table.transaction_counters.name
  counters_table_arn         = aws_dynamodb_table.transaction_counters.arn
  api_clients_table_name     = aws_dynamodb_table.api_clients.name
  api_clients_table_arn      = aws_dynamodb_table.api_clients.arn
  transactions_stream_arn    = aws_dynamodb_table.transactions.stream_arn
  lambda_zip_path            = data.archive_file.lambda_zip.output_path
  lambda_zip_hash            = data.archive_file.lambda_zip.output_base64sha256
  authorizer_zip_path        = data.archive_file.authorizer_zip.output_path
  authorizer_zip_hash        = data.archive_file.authorizer_zip.output_base64sha256
  jwt_secret                 = var.jwt_secret
  token_ttl_seconds          = var.token_ttl_seconds
  other_region               = var.primary_region
}
