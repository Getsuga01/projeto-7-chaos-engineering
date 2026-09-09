# 📋 Game Day Report Template

> Use este template para documentar cada execução de Game Day.
> Copie este arquivo, renomeie com a data (ex: `gameday-2026-01-15.md`), e preencha.

---

## Informações do Experimento

| Campo | Valor |
|---|---|
| **Data** | YYYY-MM-DD |
| **Horário (UTC)** | HH:MM - HH:MM |
| **Experiment ID** | `uuid` |
| **Tipo de Falha** | `pause-replication` |
| **Duração Planejada** | ___ minutos |
| **Duração Real** | ___ minutos |
| **Operador** | Nome |
| **Ambiente** | sandbox |

---

## Configuração do Teste

### Infraestrutura
- **Região A (primária):** `us-east-1`
- **Região B (secundária):** `sa-east-1`
- **DynamoDB Billing Mode:** PAY_PER_REQUEST
- **Lambda Memory:** 256 MB
- **Lambda Runtime:** Python 3.12

### Gerador de Carga
- **Taxa:** ___ txn/s
- **Duração total:** ___ segundos
- **Check interval:** ___ segundos

---

## Hipótese

> **Antes de rodar o experimento, documente o que você ESPERA que aconteça.**

_"Ao pausar a replicação do DynamoDB Global Table por N minutos com tráfego de X txn/s, esperamos que..."_

- RPO estimado: ___ registros
- RTO estimado: ___ segundos
- Comportamento esperado na região B: ___

---

## Timeline do Experimento

| Timestamp (UTC) | Evento |
|---|---|
| `HH:MM:SS` | Gerador de carga iniciado |
| `HH:MM:SS` | Experimento registrado via API |
| `HH:MM:SS` | FIS experiment disparado |
| `HH:MM:SS` | Divergência detectada pela primeira vez |
| `HH:MM:SS` | Divergência máxima observada |
| `HH:MM:SS` | FIS experiment encerrado / replicação retomada |
| `HH:MM:SS` | Contagens convergiram |
| `HH:MM:SS` | Experimento marcado como resolvido |

---

## Resultados Medidos

| Métrica | Valor Estimado | Valor Medido | Diferença |
|---|---|---|---|
| **RTO** | ___ s | ___ s | ___ s |
| **RPO** | ___ registros | ___ registros | ___ |
| **Divergência Máxima** | ___ | ___ | ___ |
| **Transações Enviadas** | ___ | ___ | ___ |
| **Transações Falhadas** | ___ | ___ | ___ |
| **Replication Latency (pico)** | ___ ms | ___ ms | ___ |

---

## Observações do Dashboard CloudWatch

### Replication Latency
_Descreva o comportamento do gráfico de latência de replicação._

_Cole aqui um screenshot do dashboard durante o experimento._

### Lambda Errors
_Houve erros nas Lambdas durante a janela de falha?_

### API Gateway Latency
_A latência das APIs foi afetada?_

---

## Análise

### O que funcionou como esperado
- ___

### O que surpreendeu
- ___

### O que deu errado
- ___

---

## Comparação: Estimado vs. Real

> **Este é o ponto central do Game Day:** mostrar que números reais diferem dos estimados.

_Explique por que os valores medidos diferem das estimativas. O que o runbook/documentação não captura?_

---

## Ações Recomendadas

| # | Ação | Prioridade | Responsável | Status |
|---|---|---|---|---|
| 1 | ___ | Alta/Média/Baixa | ___ | Pendente |
| 2 | ___ | Alta/Média/Baixa | ___ | Pendente |
| 3 | ___ | Alta/Média/Baixa | ___ | Pendente |

---

## Limitações Deste Teste

- [ ] Pausar replicação ≠ perda total de região
- [ ] Tráfego sintético ≠ tráfego real
- [ ] Sem simulação de degradação de rede
- [ ] Sem escrita simultânea em ambas as regiões (last-writer-wins não testado)
- [ ] Outras: ___

---

## Artefatos

- [ ] Log de divergência (JSON): `divergence_log_TIMESTAMP.json`
- [ ] Screenshot do CloudWatch Dashboard
- [ ] Output do `terraform output`
- [ ] Report da API: `GET /admin/experiments/{id}/report`

---

## Aprovações

| Papel | Nome | Data |
|---|---|---|
| Operador | ___ | ___ |
| Revisor | ___ | ___ |

---

_Template baseado nas práticas de Game Day do Google DiRT e AWS Well-Architected Reliability Pillar._
