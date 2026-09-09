<#
.SYNOPSIS
    Script de destruição e limpeza segura do Projeto 7 no Windows (PowerShell)
#>

$ErrorActionPreference = "Stop"

Write-Host "======================================================" -ForegroundColor Red
Write-Host "🧹 TEARDOWN — Destruição dos Recursos Multi-Região" -ForegroundColor Red
Write-Host "======================================================" -ForegroundColor Red

$confirmation = Read-Host "Você tem certeza que deseja destruir todos os recursos do Projeto 7? (S/N)"
if ($confirmation -ne "S" -and $confirmation -ne "s" -and $confirmation -ne "Y" -and $confirmation -ne "y") {
    Write-Host "Operação cancelada pelo usuário." -ForegroundColor Yellow
    exit 0
}

$PSScriptRootLocal = Split-Path -Parent $MyInvocation.MyCommand.Definition
$TerraformDir = Join-Path (Split-Path -Parent $PSScriptRootLocal) "terraform"

Push-Location $TerraformDir
try {
    Write-Host "`nExecutando terraform destroy..." -ForegroundColor Yellow
    terraform destroy
    Write-Host "`n✔ Todos os recursos foram removidos com sucesso. Nenhum custo restante!" -ForegroundColor Green
} finally {
    Pop-Location
}
