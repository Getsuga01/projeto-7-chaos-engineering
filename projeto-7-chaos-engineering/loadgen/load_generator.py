#!/usr/bin/env python3
"""
Projeto 7 — Gerador de Carga para Game Day
============================================

Envia transações continuamente para a região primária e monitora a contagem
em ambas as regiões para detectar divergência durante experimentos de chaos.

Uso:
    python load_generator.py \
        --region-a-url https://xxxxx.execute-api.us-east-1.amazonaws.com \
        --region-b-url https://xxxxx.execute-api.sa-east-1.amazonaws.com \
        --rate 2 \
        --duration 300

Argumentos:
    --region-a-url    URL do API Gateway na região A (primária)
    --region-b-url    URL do API Gateway na região B (secundária)
    --rate            Transações por segundo (padrão: 1)
    --duration        Duração total em segundos (padrão: 300 = 5 min)
    --check-interval  Intervalo entre verificações de divergência em segundos (padrão: 5)
"""

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime, timezone

try:
    import aiohttp
except ImportError:
    print("❌ Dependência 'aiohttp' não encontrada.")
    print("   Instale com: pip install aiohttp")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuração de cores para terminal
# ---------------------------------------------------------------------------

class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


# ---------------------------------------------------------------------------
# Gerador de carga
# ---------------------------------------------------------------------------

class LoadGenerator:
    """Gerador de carga assíncrono para o Game Day."""

    def __init__(
        self,
        region_a_url: str,
        region_b_url: str,
        rate: float = 1.0,
        duration: int = 300,
        check_interval: int = 5,
    ):
        self.region_a_url = region_a_url.rstrip("/")
        self.region_b_url = region_b_url.rstrip("/")
        self.rate = rate
        self.duration = duration
        self.check_interval = check_interval

        # Contadores
        self.transactions_sent = 0
        self.transactions_failed = 0
        self.max_divergence = 0
        self.divergence_history: list[dict] = []

        # Estado
        self.running = True
        self.start_time = 0.0

    async def send_transaction(self, session: aiohttp.ClientSession) -> bool:
        """Envia uma transação para a região A."""
        payload = {
            "amount": round(random.uniform(10.0, 10000.0), 2),
            "description": f"loadgen-txn-{self.transactions_sent + 1}-{int(time.time())}",
        }

        try:
            async with session.post(
                f"{self.region_a_url}/transactions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 201:
                    self.transactions_sent += 1
                    return True
                else:
                    self.transactions_failed += 1
                    body = await resp.text()
                    print(
                        f"  {Colors.YELLOW}⚠ POST /transactions → {resp.status}: {body[:100]}{Colors.RESET}"
                    )
                    return False
        except Exception as e:
            self.transactions_failed += 1
            print(f"  {Colors.RED}✗ Erro ao enviar transação: {e}{Colors.RESET}")
            return False

    async def check_counts(self, session: aiohttp.ClientSession) -> dict | None:
        """Consulta a contagem de transações em ambas as regiões."""
        counts = {}

        for label, url in [("A", self.region_a_url), ("B", self.region_b_url)]:
            try:
                async with session.get(
                    f"{url}/transactions/count",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        counts[label] = data.get("count", -1)
                    else:
                        counts[label] = -1
            except Exception:
                counts[label] = -1

        if counts.get("A", -1) >= 0 and counts.get("B", -1) >= 0:
            divergence = abs(counts["A"] - counts["B"])
            self.max_divergence = max(self.max_divergence, divergence)

            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_s": round(time.time() - self.start_time, 1),
                "count_a": counts["A"],
                "count_b": counts["B"],
                "divergence": divergence,
            }
            self.divergence_history.append(record)
            return record

        return None

    async def transaction_loop(self, session: aiohttp.ClientSession) -> None:
        """Loop principal de envio de transações."""
        interval = 1.0 / self.rate if self.rate > 0 else 1.0

        while self.running:
            await self.send_transaction(session)
            await asyncio.sleep(interval)

    async def monitoring_loop(self, session: aiohttp.ClientSession) -> None:
        """Loop de monitoramento de divergência."""
        while self.running:
            await asyncio.sleep(self.check_interval)

            record = await self.check_counts(session)
            if record:
                elapsed = record["elapsed_s"]
                div = record["divergence"]

                # Escolhe cor baseado na divergência
                if div == 0:
                    color = Colors.GREEN
                    icon = "✓"
                elif div < 10:
                    color = Colors.YELLOW
                    icon = "△"
                else:
                    color = Colors.RED
                    icon = "✗"

                print(
                    f"  {Colors.DIM}[{elapsed:>7.1f}s]{Colors.RESET} "
                    f"Região A: {Colors.CYAN}{record['count_a']:>6}{Colors.RESET} | "
                    f"Região B: {Colors.CYAN}{record['count_b']:>6}{Colors.RESET} | "
                    f"Divergência: {color}{icon} {div}{Colors.RESET}"
                )

    async def timer_loop(self) -> None:
        """Encerra a execução após a duração configurada."""
        await asyncio.sleep(self.duration)
        self.running = False

    async def run(self) -> None:
        """Execução principal do gerador de carga."""
        self.start_time = time.time()

        print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}🔬 GERADOR DE CARGA — Game Day{Colors.RESET}")
        print(f"{'='*70}")
        print(f"  Região A (escrita): {Colors.CYAN}{self.region_a_url}{Colors.RESET}")
        print(f"  Região B (leitura): {Colors.CYAN}{self.region_b_url}{Colors.RESET}")
        print(f"  Taxa: {Colors.GREEN}{self.rate} txn/s{Colors.RESET}")
        print(f"  Duração: {Colors.GREEN}{self.duration}s{Colors.RESET}")
        print(f"  Check interval: {Colors.GREEN}{self.check_interval}s{Colors.RESET}")
        print(f"{'='*70}\n")

        # Health check antes de começar
        print(f"  {Colors.DIM}Verificando conectividade...{Colors.RESET}")
        async with aiohttp.ClientSession() as session:
            for label, url in [("A", self.region_a_url), ("B", self.region_b_url)]:
                try:
                    async with session.get(
                        f"{url}/health",
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(
                                f"  {Colors.GREEN}✓{Colors.RESET} Região {label}: "
                                f"{data.get('region', 'ok')} — healthy"
                            )
                        else:
                            print(
                                f"  {Colors.RED}✗{Colors.RESET} Região {label}: "
                                f"status {resp.status}"
                            )
                            return
                except Exception as e:
                    print(
                        f"  {Colors.RED}✗{Colors.RESET} Região {label}: {e}"
                    )
                    return

        print(f"\n  {Colors.BOLD}Iniciando tráfego...{Colors.RESET}\n")

        async with aiohttp.ClientSession() as session:
            tasks = [
                asyncio.create_task(self.transaction_loop(session)),
                asyncio.create_task(self.monitoring_loop(session)),
                asyncio.create_task(self.timer_loop()),
            ]

            # Espera o timer encerrar
            await asyncio.gather(*tasks, return_exceptions=True)

        # Relatório final
        elapsed = time.time() - self.start_time
        print(f"\n{'='*70}")
        print(f"{Colors.BOLD}📊 RELATÓRIO FINAL{Colors.RESET}")
        print(f"{'='*70}")
        print(f"  Duração total:         {elapsed:.1f}s")
        print(f"  Transações enviadas:   {Colors.GREEN}{self.transactions_sent}{Colors.RESET}")
        print(f"  Transações falhadas:   {Colors.RED}{self.transactions_failed}{Colors.RESET}")
        print(f"  Taxa efetiva:          {self.transactions_sent / max(elapsed, 1):.2f} txn/s")
        print(f"  Divergência máxima:    {Colors.YELLOW}{self.max_divergence}{Colors.RESET}")
        print(f"{'='*70}\n")

        # Salva histórico de divergência em arquivo
        output_file = f"divergence_log_{int(time.time())}.json"
        with open(output_file, "w") as f:
            json.dump(
                {
                    "summary": {
                        "transactions_sent": self.transactions_sent,
                        "transactions_failed": self.transactions_failed,
                        "max_divergence": self.max_divergence,
                        "duration_seconds": elapsed,
                        "rate_target": self.rate,
                        "rate_effective": self.transactions_sent / max(elapsed, 1),
                    },
                    "divergence_history": self.divergence_history,
                },
                f,
                indent=2,
            )
        print(f"  📁 Log de divergência salvo em: {Colors.CYAN}{output_file}{Colors.RESET}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Gerador de carga para o Game Day do Projeto 7",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Baseline: 1 txn/s por 5 minutos
  python load_generator.py --region-a-url https://xxx.execute-api.us-east-1.amazonaws.com --region-b-url https://xxx.execute-api.sa-east-1.amazonaws.com

  # Carga alta: 5 txn/s por 10 minutos
  python load_generator.py --region-a-url URL_A --region-b-url URL_B --rate 5 --duration 600
        """,
    )

    parser.add_argument(
        "--region-a-url",
        required=True,
        help="URL do API Gateway na região A (primária — recebe as escritas)",
    )
    parser.add_argument(
        "--region-b-url",
        required=True,
        help="URL do API Gateway na região B (secundária — usada para leitura/comparação)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Transações por segundo (padrão: 1)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Duração total em segundos (padrão: 300 = 5 min)",
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=5,
        help="Intervalo entre verificações de divergência em segundos (padrão: 5)",
    )

    args = parser.parse_args()

    generator = LoadGenerator(
        region_a_url=args.region_a_url,
        region_b_url=args.region_b_url,
        rate=args.rate,
        duration=args.duration,
        check_interval=args.check_interval,
    )

    try:
        asyncio.run(generator.run())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠ Interrompido pelo usuário{Colors.RESET}")
        generator.running = False


if __name__ == "__main__":
    main()
