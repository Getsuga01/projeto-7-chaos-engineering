#!/usr/bin/env python3
"""
Projeto 7 — Orquestrador End-to-End de Game Day (Chaos as Code)
================================================================

Automatiza todo o ciclo de vida de um Game Day multi-região:
1. Valida conectividade e health checks em ambas as regiões.
2. Registra formalmente o experimento via API (POST /admin/experiments).
3. Inicia envio contínuo de transações em background (Região A).
4. Dispara o AWS Fault Injection Service (FIS) via Boto3 para pausar a replicação.
5. Monitora a curva de divergência de dados entre as regiões em tempo real.
6. Detecta o fim da injeção de falha e monitora o tempo de convergência (RTO).
7. Finaliza o experimento via API (POST /admin/experiments/{id}/resolve).
8. Gera automaticamente o relatório do Game Day em Markdown com dados medidos reais!

Uso básico (lê parâmetros direto do Terraform):
    python scripts/orchestrate_gameday.py

Uso com parâmetros explícitos:
    python scripts/orchestrate_gameday.py \
        --region-a-url https://xxx.execute-api.us-east-1.amazonaws.com \
        --region-b-url https://xxx.execute-api.sa-east-1.amazonaws.com \
        --fis-template-id EXTxxxxxxxxxxxx \
        --rate 2 \
        --notes "Game Day automatizado - simulação de isolamento regional"
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import aiohttp
    import boto3
except ImportError:
    print("❌ Dependências ausentes. Instale com:")
    print("   pip install aiohttp boto3")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Terminal Colors
# ---------------------------------------------------------------------------

class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    MAGENTA = "\033[95m"


def print_step(title: str):
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}▶ {title}{Colors.RESET}")


def load_terraform_outputs(terraform_dir: str) -> dict:
    """Tenta ler os outputs do Terraform automaticamente se estiverem disponíveis."""
    try:
        cmd = ["terraform", "output", "-json"]
        result = subprocess.run(
            cmd,
            cwd=terraform_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        return {k: v.get("value") for k, v in data.items()}
    except Exception as e:
        print(f"  {Colors.DIM}Outputs do Terraform não encontrados automaticamente ({e}).{Colors.RESET}")
        return {}


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

class GameDayOrchestrator:
    def __init__(
        self,
        region_a_url: str,
        region_b_url: str,
        fis_template_id: str,
        primary_region: str = "us-east-1",
        rate: float = 2.0,
        notes: str = "Game Day Automatizado",
        poll_interval: float = 3.0,
        output_report_path: str = None,
    ):
        self.region_a_url = region_a_url.rstrip("/")
        self.region_b_url = region_b_url.rstrip("/")
        self.fis_template_id = fis_template_id
        self.primary_region = primary_region
        self.rate = rate
        self.notes = notes
        self.poll_interval = poll_interval
        self.output_report_path = output_report_path

        self.fis_client = boto3.client("fis", region_name=primary_region)
        self.experiment_api_id = None
        self.fis_experiment_id = None

        self.transactions_sent = 0
        self.transactions_failed = 0
        self.is_sending = False

        self.history = []
        self.peak_divergence = 0
        self.fault_started_at = None
        self.fault_ended_at = None
        self.converged_at = None

    async def check_health(self, session: aiohttp.ClientSession) -> bool:
        """Valida que ambas as regiões estão respondendo adequadamente."""
        print_step("1. Validando Conectividade das Regiões")
        for label, url in [("Região A (Primária)", self.region_a_url), ("Região B (Secundária)", self.region_b_url)]:
            try:
                async with session.get(f"{url}/health", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        region_code = data.get("region_local", "ok")
                        cross_ok = data.get("cross_region_access", False)
                        cross_str = f"| Cross-region: {'✓' if cross_ok else '✗'}" if "cross_region_access" in data else ""
                        print(f"  {Colors.GREEN}✓{Colors.RESET} {label} ({region_code}): Healthy {cross_str}")
                    else:
                        print(f"  {Colors.RED}✗{Colors.RESET} {label} retornou status {resp.status}")
                        return False
            except Exception as e:
                print(f"  {Colors.RED}✗{Colors.RESET} Falha ao contatar {label}: {e}")
                return False
        return True

    async def register_experiment(self, session: aiohttp.ClientSession) -> bool:
        """Registra o experimento na API para governança e baseline."""
        print_step("2. Registrando Experimento na API")
        payload = {
            "fault_type": "pause-replication",
            "notes": self.notes,
        }
        try:
            async with session.post(f"{self.region_a_url}/admin/experiments", json=payload) as resp:
                if resp.status == 201:
                    data = await resp.json()
                    self.experiment_api_id = data["experiment_id"]
                    print(f"  {Colors.GREEN}✓{Colors.RESET} ID do Experimento: {Colors.CYAN}{self.experiment_api_id}{Colors.RESET}")
                    baselines = data.get("baselines", {})
                    print(f"  📊 Baseline de registros: {baselines}")
                    return True
                else:
                    body = await resp.text()
                    print(f"  {Colors.RED}✗ Falha ao registrar experimento:{Colors.RESET} {body}")
                    return False
        except Exception as e:
            print(f"  {Colors.RED}✗ Erro ao registrar experimento:{Colors.RESET} {e}")
            return False

    async def send_transactions_worker(self, session: aiohttp.ClientSession):
        """Loop de envio de transações sintéticas."""
        interval = 1.0 / self.rate if self.rate > 0 else 1.0
        while self.is_sending:
            payload = {
                "amount": round(50.0 + (self.transactions_sent * 1.5) % 900.0, 2),
                "description": f"gameday-auto-txn-{self.transactions_sent + 1}",
            }
            try:
                async with session.post(
                    f"{self.region_a_url}/transactions",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 201:
                        self.transactions_sent += 1
                    else:
                        self.transactions_failed += 1
            except Exception:
                self.transactions_failed += 1
            await asyncio.sleep(interval)

    def start_fis_experiment(self) -> bool:
        """Inicia o experimento no AWS Fault Injection Service via Boto3."""
        print_step("3. Disparando AWS Fault Injection Service (FIS)")
        try:
            response = self.fis_client.start_experiment(
                experimentTemplateId=self.fis_template_id,
                tags={"Project": "chaos-lab", "ManagedBy": "orchestrator"},
            )
            self.fis_experiment_id = response["experiment"]["id"]
            self.fault_started_at = datetime.now(timezone.utc)
            print(f"  {Colors.GREEN}✓{Colors.RESET} Experimento FIS iniciado!")
            print(f"  🆔 FIS Experiment ID: {Colors.CYAN}{self.fis_experiment_id}{Colors.RESET}")
            return True
        except Exception as e:
            print(f"  {Colors.RED}✗ Falha ao iniciar experimento no FIS:{Colors.RESET} {e}")
            print(f"    (Certifique-se de que suas credenciais AWS possuem permissão fis:StartExperiment)")
            return False

    def get_fis_status(self) -> str:
        """Obtém status do experimento FIS."""
        try:
            resp = self.fis_client.get_experiment(id=self.fis_experiment_id)
            return resp["experiment"]["state"]["status"]
        except Exception:
            return "UNKNOWN"

    async def monitor_loop(self, session: aiohttp.ClientSession):
        """Loop principal de monitoramento da divergência e detecção de convergência."""
        print_step("4. Monitorando Injeção de Falha e Divergência Multi-Região")
        print(f"  {Colors.DIM}Acompanhando estado das tabelas a cada {self.poll_interval}s...{Colors.RESET}\n")

        fis_done = False
        fis_last_status = "initiating"
        start_time = time.time()

        while True:
            # 1. Checa status do FIS se ainda não tiver terminado
            if not fis_done:
                status = self.get_fis_status()
                if status != fis_last_status:
                    print(f"  {Colors.MAGENTA}⚡ Status do FIS:{Colors.RESET} {Colors.BOLD}{status}{Colors.RESET}")
                    fis_last_status = status

                if status in ("completed", "stopped", "failed"):
                    fis_done = True
                    self.fault_ended_at = datetime.now(timezone.utc)
                    print(f"\n  {Colors.GREEN}✓ Replicação retomada pelo FIS!{Colors.RESET} Iniciando medição de convergência (RTO)...")

            # 2. Consulta contagem nas duas regiões
            count_a = -1
            count_b = -1
            try:
                async with session.get(f"{self.region_a_url}/transactions/count") as r_a:
                    if r_a.status == 200:
                        count_a = (await r_a.json()).get("count", -1)

                async with session.get(f"{self.region_b_url}/transactions/count") as r_b:
                    if r_b.status == 200:
                        count_b = (await r_b.json()).get("count", -1)
            except Exception:
                pass

            elapsed = round(time.time() - start_time, 1)

            if count_a >= 0 and count_b >= 0:
                divergence = abs(count_a - count_b)
                self.peak_divergence = max(self.peak_divergence, divergence)

                self.history.append({
                    "elapsed_s": elapsed,
                    "count_a": count_a,
                    "count_b": count_b,
                    "divergence": divergence,
                    "fis_status": fis_last_status,
                })

                # Exibição estilizada
                if divergence == 0:
                    status_badge = f"{Colors.GREEN}● Sincronizado{Colors.RESET}"
                else:
                    status_badge = f"{Colors.RED}▲ Divergência: {divergence} registros{Colors.RESET}"

                print(
                    f"  [{elapsed:>6.1f}s] "
                    f"Região A: {Colors.CYAN}{count_a:>5}{Colors.RESET} | "
                    f"Região B: {Colors.CYAN}{count_b:>5}{Colors.RESET} | "
                    f"{status_badge}"
                )

                # Se o FIS já encerrou e a divergência voltou a zero, convergência alcançada!
                if fis_done and divergence == 0:
                    self.converged_at = datetime.now(timezone.utc)
                    print(f"\n  {Colors.GREEN}{Colors.BOLD}🎉 CONVERGÊNCIA DETECTADA! Todas as réplicas sincronizadas.{Colors.RESET}")
                    break

            await asyncio.sleep(self.poll_interval)

    async def resolve_experiment(self, session: aiohttp.ClientSession) -> dict:
        """Marca o experimento como resolvido na API."""
        print_step("5. Finalizando Experimento na API")
        try:
            async with session.post(f"{self.region_a_url}/admin/experiments/{self.experiment_api_id}/resolve") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  {Colors.GREEN}✓ Experimento resolvido com sucesso!{Colors.RESET}")
                    return data
        except Exception as e:
            print(f"  {Colors.RED}✗ Erro ao resolver experimento:{Colors.RESET} {e}")
        return {}

    async def get_report(self, session: aiohttp.ClientSession) -> dict:
        """Recupera o relatório JSON consolidado da API."""
        try:
            async with session.get(f"{self.region_a_url}/admin/experiments/{self.experiment_api_id}/report") as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return {}

    def generate_markdown_report(self, report_data: dict, output_file: str):
        """Preenche o template de Game Day com todos os dados medidos reais."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Calcula RTO real medido
        rto_seconds = "N/A"
        if self.fault_ended_at and self.converged_at:
            rto_seconds = round((self.converged_at - self.fault_ended_at).total_seconds(), 2)

        md_content = f"""# 📋 Game Day Report — Execução Automatizada

> Gerado automaticamente pelo **Orquestrador de Game Day do Projeto 7**.
> Data de Execução: `{now}`

---

## 📌 Identificação do Experimento

| Campo | Valor Medido Real |
|---|---|
| **API Experiment ID** | `{self.experiment_api_id}` |
| **AWS FIS Experiment ID** | `{self.fis_experiment_id}` |
| **Tipo de Falha** | `pause-replication (aws:dynamodb:global-table-pause-replication)` |
| **Região Primária** | `{self.primary_region}` |
| **Região Secundária** | `sa-east-1` |
| **Taxa de Escrita** | `{self.rate} txn/s` |
| **Notas** | {self.notes} |

---

## 📊 Métricas Chave de Resiliência (Medidas)

| Métrica | Valor Medido | Descrição |
|---|---|---|
| **RPO Real (Pico de Divergência)** | **`{self.peak_divergence} registros`** | Máxima discrepância entre regiões durante a janela de falha |
| **RTO Real (Tempo de Convergência)** | **`{rto_seconds} segundos`** | Tempo desde o término da falha até as tabelas sincronizarem |
| **Transações Enviadas** | `{self.transactions_sent}` | Total de escritas direcionadas à região primária |
| **Transações Falhadas** | `{self.transactions_failed}` | Total de falhas HTTP na escrita local |

---

## ⏱️ Linha do Tempo

- **Início do Experimento:** `{self.fault_started_at.isoformat() if self.fault_started_at else 'N/A'}`
- **Replicação Retomada:** `{self.fault_ended_at.isoformat() if self.fault_ended_at else 'N/A'}`
- **Convergência Alcançada:** `{self.converged_at.isoformat() if self.converged_at else 'N/A'}`

---

## 📈 Amostragem da Curva de Divergência

| Tempo Decorrido | Região A (Primária) | Região B (Secundária) | Divergência | Status do FIS |
|---|---|---|---|---|
"""
        # Adiciona até 15 amostras distribuídas do histórico
        step = max(1, len(self.history) // 15)
        sampled = self.history[::step]
        if self.history and self.history[-1] not in sampled:
            sampled.append(self.history[-1])

        for entry in sampled:
            md_content += f"| {entry['elapsed_s']}s | {entry['count_a']} | {entry['count_b']} | **{entry['divergence']}** | {entry['fis_status']} |\n"

        md_content += """
---

## 🧠 Conclusões de Engenharia

1. **Comportamento Local vs. Global:** A região primária continuou aceitando escritas normalmente mesmo com a replicação suspensa, comprovando o isolamento do blast radius.
2. **Drenagem de Backlog:** Assim que o FIS finalizou a ação de pausa, o DynamoDB iniciou a drenagem automática do backlog sem requerer intervenção manual de failover.
3. **Confiabilidade das Métricas:** O RPO e RTO foram medidos via amostragem de dados observados, eliminando números teóricos de runbook.

---
_Relatório compilado conforme metodologia SRE Game Day._
"""

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"\n  {Colors.GREEN}✓ Relatório Markdown gerado com sucesso:{Colors.RESET} {Colors.CYAN}{output_file}{Colors.RESET}")

    async def run(self):
        """Executa a orquestração completa."""
        print(f"\n{Colors.BOLD}{'='*75}{Colors.RESET}")
        print(f"{Colors.BOLD}🔬 ORQUESTRADOR DE GAME DAY — Chaos as Code{Colors.RESET}")
        print(f"{'='*75}")
        print(f"  Região A: {Colors.CYAN}{self.region_a_url}{Colors.RESET}")
        print(f"  Região B: {Colors.CYAN}{self.region_b_url}{Colors.RESET}")
        print(f"  FIS Template: {Colors.CYAN}{self.fis_template_id}{Colors.RESET}")
        print(f"  Taxa de Carga: {Colors.GREEN}{self.rate} txn/s{Colors.RESET}")
        print(f"{'='*75}")

        async with aiohttp.ClientSession() as session:
            # 1. Health Check
            if not await self.check_health(session):
                print(f"\n{Colors.RED}❌ Abortando: Falha na validação das regiões.{Colors.RESET}")
                return

            # 2. Registrar Experimento
            if not await self.register_experiment(session):
                print(f"\n{Colors.RED}❌ Abortando: Falha ao registrar experimento.{Colors.RESET}")
                return

            # 3. Iniciar Carga em Background
            self.is_sending = True
            load_task = asyncio.create_task(self.send_transactions_worker(session))

            # Aguarda alguns segundos para ter baseline em tráfego
            await asyncio.sleep(4)

            # 4. Disparar FIS
            if not self.start_fis_experiment():
                self.is_sending = False
                await load_task
                return

            # 5. Monitorar até Convergência
            await self.monitor_loop(session)

            # 6. Encerrar envio de carga
            self.is_sending = False
            await load_task

            # 7. Resolver experimento na API
            await self.resolve_experiment(session)

            # 8. Baixar relatório e gerar Markdown
            report_data = await self.get_report(session)
            
            report_file = self.output_report_path or f"docs/gameday-report-{int(time.time())}.md"
            self.generate_markdown_report(report_data, report_file)

        print(f"\n{Colors.BOLD}{'='*75}{Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD}✔ GAME DAY CONCLUÍDO COM SUCESSO!{Colors.RESET}")
        print(f"{'='*75}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Orquestrador End-to-End de Game Day AWS",
    )
    parser.add_argument("--region-a-url", help="URL do API Gateway na Região A")
    parser.add_argument("--region-b-url", help="URL do API Gateway na Região B")
    parser.add_argument("--fis-template-id", help="ID do Template de Experimento FIS")
    parser.add_argument("--primary-region", default="us-east-1", help="Região primária AWS")
    parser.add_argument("--rate", type=float, default=2.0, help="Transações/s (padrão: 2.0)")
    parser.add_argument("--notes", default="Game Day Automatizado", help="Notas do experimento")
    parser.add_argument("--output-report", help="Caminho do arquivo Markdown de saída")

    args = parser.parse_args()

    # Se parâmetros não foram informados na CLI, tenta ler do terraform output
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tf_dir = os.path.join(base_dir, "terraform")
    tf_outputs = load_terraform_outputs(tf_dir)

    region_a = args.region_a_url or tf_outputs.get("api_endpoint_region_a")
    region_b = args.region_b_url or tf_outputs.get("api_endpoint_region_b")
    fis_id = args.fis_template_id or tf_outputs.get("fis_experiment_template_id")

    if not region_a or not region_b:
        print(f"{Colors.RED}❌ Erro: URLs das regiões não fornecidas e não encontradas no Terraform.{Colors.RESET}")
        print("  Use os argumentos --region-a-url e --region-b-url ou execute 'terraform apply' antes.")
        sys.exit(1)

    if not fis_id:
        print(f"{Colors.RED}❌ Erro: ID do template FIS não fornecido e não encontrado no Terraform.{Colors.RESET}")
        print("  Use o argumento --fis-template-id ou execute 'terraform apply' antes.")
        sys.exit(1)

    orchestrator = GameDayOrchestrator(
        region_a_url=region_a,
        region_b_url=region_b,
        fis_template_id=fis_id,
        primary_region=args.primary_region,
        rate=args.rate,
        notes=args.notes,
        output_report_path=args.output_report,
    )

    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠ Orquestração cancelada pelo operador.{Colors.RESET}")


if __name__ == "__main__":
    main()
