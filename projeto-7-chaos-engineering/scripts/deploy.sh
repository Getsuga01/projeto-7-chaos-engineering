#!/usr/bin/env bash
set -e

echo -e "\033[1;36m======================================================\033[0m"
echo -e "\033[1;36m🚀 DEPLOY — Laboratório de Resiliência Multi-Região\033[0m"
echo -e "\033[1;36m======================================================\033[0m"

echo -e "\n\033[1;33m[1/4] Verificando pré-requisitos...\033[0m"
command -v terraform >/dev/null 2>&1 || { echo "Terraform não encontrado no PATH."; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "AWS CLI não encontrado no PATH."; exit 1; }

echo -e "\033[1;33m[2/4] Validando credenciais AWS...\033[0m"
aws sts get-caller-identity >/dev/null || { echo "Falha ao autenticar na AWS."; exit 1; }
echo -e "  \033[32m✓ Credenciais AWS ativas!\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../terraform"

echo -e "\n\033[1;33m[3/4] Inicializando Terraform em $TF_DIR...\033[0m"
cd "$TF_DIR"
terraform init
terraform validate

echo -e "\n\033[1;33m[4/4] Aplicando infraestrutura...\033[0m"
terraform apply

echo -e "\n\033[1;32m✔ Infraestrutura multi-região implantada com sucesso!\033[0m"
terraform output
