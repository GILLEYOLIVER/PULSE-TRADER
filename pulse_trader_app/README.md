# PULSE TRADER — Engine + Plugins + Risk + Journal (MVP pronto para evoluir)

Este projeto é um esqueleto **rodável** (sem ProfitDLL) que já entrega:
- Motor **event-driven** com fila (ticks / notícias)
- Estratégias plugáveis
- **Risk Manager** (risco por trade, max loss diário, pausa por sequência de stops)
- Execução **Paper Trading** (simulada)
- **Diário de trades** em PostgreSQL (opcional) + logs estruturados
- UI simples em **CustomTkinter** para operar em 3 segundos (Paper por padrão)

> Integração com Profit Pro: o módulo `adapters/profitdll.py` é um **adapter** com interface pronta.  
> Você só precisa “plugar” as chamadas reais da DLL no lugar dos stubs.

---

## 1) Como rodar rápido (sem Profit Pro)
1. Crie venv e instale dependências:
```bash
pip install -r requirements.txt
```

2. Rode:
```bash
python run_app.py
```

Você vai ver:
- Feed simulado gerando ticks
- Estratégia simples gerando sinais
- Risk calculando contratos
- Paper executando (apenas simulação)
- UI exibindo o “o que fazer agora”

---

## 2) PostgreSQL (opcional, recomendado)
Defina a variável de ambiente:
- Windows PowerShell:
```powershell
$env:PULSE_PG_DSN="dbname=BANCO_OPERA user=postgres password=123 host=localhost port=5432"
```

- Linux/Mac:
```bash
export PULSE_PG_DSN="dbname=BANCO_OPERA user=postgres password=123 host=localhost port=5432"
```

Ao iniciar, o app cria as tabelas (schema `pulse`) automaticamente.

---

## 3) Onde colocar suas estratégias
Crie novos arquivos em `trader_tool/strategies/` e registre no `engine.py`.

---

## 4) Segurança operacional (por design)
- Inicia sempre em **PAPER**
- Possui **Kill Switch** (pausar) e bloqueios por regra no Risk
- Logs estruturados + journal no banco

---

## 5) Próximos passos (sua evolução)
- Substituir `adapters/sim_feed.py` por `adapters/profitdll.py`
- Implementar `alerts/telegram.py`
- Adicionar Replay (histórico → “ao vivo”)
- Criar dashboards de métricas no UI (win rate, drawdown, etc.)


## V2 (sinais visíveis)
- Adicionada estratégia `Momentum (SMA Cross)` que sempre explica BUY/SELL/WAIT.
- Feed simulado agora inclui bid/ask sizes para testar imbalance.
- UI mostra painel de **Diagnóstico** (por que está em WAIT, ATR, news risk, cooldown etc.).
