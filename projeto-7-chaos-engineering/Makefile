# Projeto 7 — Makefile
# Comandos convenientes para desenvolvimento, teste e deploy

.PHONY: help fmt lint test unit-test integration-test deploy plan apply destroy clean install-dev

# Variáveis
TF_DIR := terraform
SRC_DIR := src
LOADGEN_DIR := loadgen
SCRIPTS_DIR := scripts
TESTS_DIR := tests
PYTHON := python3
PIP := pip3

# Default target
help:
	@echo "Projeto 7 — Laboratório de Resiliência Multi-Região"
	@echo ""
	@echo "Comandos disponíveis:"
	@echo "  make fmt              - Formatar código (Terraform + Python)"
	@echo "  make lint             - Lint completo (Ruff + MyPy + Terraform)"
	@echo "  make test             - Executar todos os testes"
	@echo "  make unit-test        - Testes unitários com coverage"
	@echo "  make integration-test - Testes de integração (LocalStack)"
	@echo "  make plan             - Terraform plan"
	@echo "  make apply            - Terraform apply"
	@echo "  make destroy          - Terraform destroy"
	@echo "  make deploy           - Deploy completo (plan + apply)"
	@echo "  make install-dev      - Instalar dependências de desenvolvimento"
	@echo "  make clean            - Limpar arquivos gerados"
	@echo "  make gameday          - Executar Game Day automatizado"
	@echo "  make loadgen          - Executar gerador de carga manual"

# =============================================================================
# Formatação e Lint
# =============================================================================

fmt:
	@echo "🔧 Formatando código..."
	cd $(TF_DIR) && terraform fmt -recursive
	ruff format $(SRC_DIR) $(LOADGEN_DIR) $(SCRIPTS_DIR) $(TESTS_DIR)

lint:
	@echo "🔍 Executando lint..."
	ruff check $(SRC_DIR) $(LOADGEN_DIR) $(SCRIPTS_DIR) $(TESTS_DIR) --output-format=github
	mypy $(SRC_DIR)/lambda/lambda_function.py $(SRC_DIR)/stream_processor/stream_processor.py $(SRC_DIR)/authorizer/authorizer.py --ignore-missing-imports
	cd $(TF_DIR) && terraform validate

# =============================================================================
# Testes
# =============================================================================

test: unit-test integration-test

unit-test:
	@echo "🧪 Executando testes unitários..."
	pytest $(TESTS_DIR)/unit/ -v --cov=$(SRC_DIR) --cov-report=term-missing --cov-report=html

integration-test:
	@echo "🧪 Executando testes de integração (requer LocalStack)..."
	@if ! curl -s http://localhost:4566/_localstack/health | grep -q '"dynamodb": "running"'; then \
		echo "❌ LocalStack não está rodando. Inicie com: docker run -d -p 4566:4566 localstack/localstack:3.5"; \
		exit 1; \
	fi
	AWS_ENDPOINT_URL=http://localhost:4566 \
	AWS_ACCESS_KEY_ID=test \
	AWS_SECRET_ACCESS_KEY=test \
	AWS_DEFAULT_REGION=us-east-1 \
	pytest $(TESTS_DIR)/integration/ -v --tb=short

# =============================================================================
# Terraform
# =============================================================================

plan:
	@echo "📋 Terraform Plan..."
	cd $(TF_DIR) && terraform init && terraform plan

apply:
	@echo "🚀 Terraform Apply..."
	cd $(TF_DIR) && terraform apply

destroy:
	@echo "🧨 Terraform Destroy..."
	cd $(TF_DIR) && terraform destroy

deploy: plan apply
	@echo "✅ Deploy completo!"

# =============================================================================
# Desenvolvimento
# =============================================================================

install-dev:
	@echo "📦 Instalando dependências de desenvolvimento..."
	$(PIP) install --upgrade pip
	$(PIP) install ruff mypy pytest pytest-cov pytest-mock moto bandit safety
	$(PIP) install -r $(SRC_DIR)/lambda/requirements.txt
	$(PIP) install -r $(LOADGEN_DIR)/requirements.txt

clean:
	@echo "🧹 Limpando arquivos gerados..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(TF_DIR)/.terraform.lock.hcl $(TF_DIR)/.terraform 2>/dev/null || true
	rm -rf dist/ 2>/dev/null || true

# =============================================================================
# Game Day & Load Generation
# =============================================================================

gameday:
	@echo "🎮 Executando Game Day automatizado..."
	cd $(SCRIPTS_DIR) && $(PYTHON) orchestrate_gameday.py

loadgen:
	@echo "⚡ Executando gerador de carga..."
	@if [ -z "$(REGION_A_URL)" ] || [ -z "$(REGION_B_URL)" ]; then \
		echo "Uso: make loadgen REGION_A_URL=<url> REGION_B_URL=<url> [RATE=2] [DURATION=300]"; \
		exit 1; \
	fi
	cd $(LOADGEN_DIR) && $(PYTHON) load_generator.py \
		--region-a-url "$(REGION_A_URL)" \
		--region-b-url "$(REGION_B_URL)" \
		--rate "$(RATE)" \
		--duration "$(DURATION)"

# =============================================================================
# Utilitários
# =============================================================================

tf-output:
	@cd $(TF_DIR) && terraform output -json

tf-validate:
	@cd $(TF_DIR) && terraform init -backend=false && terraform validate

check-deps:
	@echo "🔍 Verificando dependências desatualizadas..."
	pip list --outdated --format=columns

security-scan:
	@echo "🔒 Executando scan de segurança..."
	bandit -r $(SRC_DIR) -f json -o bandit-report.json || true
	safety check --json --output safety-report.json || true

# =============================================================================
# Documentação
# =============================================================================

docs:
	@echo "📚 Gerando documentação..."
	@echo "TODO: Implementar geração de docs (ex: terraform-docs, pdoc)"

# =============================================================================
# CI Local (simula GitHub Actions)
# =============================================================================

ci-local: fmt lint unit-test
	@echo "✅ CI local passou!"