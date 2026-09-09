# =============================================================================
# Backend de state — S3 + DynamoDB Lock (Recomendado para equipe/produção)
# =============================================================================
# Para usar: descomente o bloco abaixo e execute `terraform init -migrate-state`
# O bucket e a tabela de lock são criados pelo módulo backend-bootstrap (abaixo)
# =============================================================================

terraform {
  backend "s3" {
    bucket         = "chaos-lab-terraform-state-${var.environment}"
    key            = "chaos-lab/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks-${var.environment}"
    encrypt        = true
  }
}

# =============================================================================
# Bootstrap do Backend (S3 Bucket + DynamoDB Lock Table)
# =============================================================================
# Execute estes recursos UMA VEZ para criar o backend, depois comente/remova
# e use o bloco terraform.backend acima.
# =============================================================================

# resource "aws_s3_bucket" "terraform_state" {
#   bucket = "chaos-lab-terraform-state-${var.environment}"
# 
#   server_side_encryption_configuration {
#     rule {
#       apply_server_side_encryption_by_default {
#         sse_algorithm = "AES256"
#       }
#     }
#   }
# 
#   versioning {
#     enabled = true
#   }
# 
#   lifecycle {
#     prevent_destroy = true
#   }
# 
#   tags = {
#     Name        = "terraform-state-${var.environment}"
#     Project     = var.project_name
#     Environment = var.environment
#     ManagedBy   = "terraform"
#   }
# }
# 
# resource "aws_dynamodb_table" "terraform_locks" {
#   name         = "terraform-locks-${var.environment}"
#   billing_mode = "PAY_PER_REQUEST"
#   hash_key     = "LockID"
# 
#   attribute {
#     name = "LockID"
#     type = "S"
#   }
# 
#   ttl {
#     attribute_name = "TTL"
#     enabled        = true
#   }
# 
#   tags = {
#     Name        = "terraform-locks-${var.environment}"
#     Project     = var.project_name
#     Environment = var.environment
#     ManagedBy   = "terraform"
#   }
# }
