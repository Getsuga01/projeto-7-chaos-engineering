<#
.SYNOPSIS
    Script de deploy automatizado do Projeto 7 no Windows (PowerShell)
#>

$ErrorActionPreference = "Stop"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "🚀 DEPLOY — Laboratório de Resiliência Multi-Região" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# 1. Checagem de ferramentas
Write-Host "`n[1/4] Verificando pré-requisitos..." -ForegroundColor Yellow
if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
    Write-Error "Terraform não encontrado no PATH. Instale o Terraform antes de prosseguir."
}
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Write-Error "AWS CLI não encontrado no PATH. Instale a AWS CLI v2."
}

# 2. Validando identidade AWS
Write-Host "[2/4] Validando credenciais AWS ativas..." -ForegroundColor Yellow
try {
    $identity = aws sts get-caller-identity | ConvertFrom-Json
    Write-Host "  Conta AWS: $($identity.Account) | ARN: $($identity.Arn)" -ForegroundColor Green
} catch {
    Write-Error "Não foi possível autenticar na AWS. Execute 'aws configure' ou configure suas variáveis de ambiente."
}

# 3. Terraform Init e Validate
$PSScriptRootLocal = Split-Path -Parent $MyInvocation.MyCommand.Definition
$TerraformDir = Join-Path (Split-Path -Parent $PSScriptRootLocal) "terraform"

Write-Host "`n[3/4] Inicializando Terraform em $TerraformDir..." -ForegroundColor Yellow
Push-Location $TerraformDir
try {
    terraform init
    terraform validate
    Write-Host "  Terraform validado com sucesso!" -ForegroundColor Green

    # 4. Terraform Apply
    Write-Host "`n[4/4] Planejando e aplicando infraestrutura..." -ForegroundColor Yellow
    terraform apply
    
    Write-Host "`n======================================================" -ForegroundColor Green
    Write-Host "✔ Infraestrutura multi-região implantada com sucesso!" -ForegroundColor Green
    Write-Host "======================================================" -ForegroundColor Green
    terraform output
} finally {
    Pop-Location
}
