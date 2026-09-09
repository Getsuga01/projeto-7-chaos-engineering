#!/usr/bin/env bash
set -e

echo -e "\033[1;31m======================================================\033[0m"
echo -e "\033[1;31m🧹 TEARDOWN — Destruição dos Recursos Multi-Região\033[0m"
echo -e "\033[1;31m======================================================\033[0m"

read -p "Você tem certeza que deseja destruir todos os recursos do Projeto 7? (s/N) " confirm
if [[ "$confirm" != [sS] && "$confirm" != [yY] ]]; then
    echo "Operação cancelada pelo usuário."
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../terraform"

cd "$TF_DIR"
terraform destroy
echo -e "\n\033[1;32m✔ Todos os recursos foram removidos com sucesso!\033[0m"
