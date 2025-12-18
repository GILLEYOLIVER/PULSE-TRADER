# PULSE-TRADER

Dashboard profissional (estilo “cockpit”) para **decisão de trade** em tempo real, com:

- **Candles** (mock por enquanto)
- **Book/ladder** (mock por enquanto)
- **Notícias globais (multi‑fonte)**: Alpha Vantage + Finnhub + GDELT
- **NewsImpactScore por ativo** (impacto/urgência com decaimento)
- **Recomendação**: `COMPRAR / VENDER / ESPERAR` + **confiança** + motivo (explicável)
- **Gestão de risco** (sizing por risco, limites)
- **Execução** em modo **paper** (a conexão com Profit Pro entra só no final)
- **Ordens manuais** com **dupla confirmação** (segurança)

> **Importante:** este app **não promete lucros**. Ele ajuda a tomar decisões com disciplina, dados e regras.
> Use **paper** para validar antes de qualquer execução real.

---

## 1) Requisitos

- Python **3.10+** (recomendado 3.11/3.12)
- Windows / macOS / Linux
- `pip` atualizado

Dependências principais:
- `customtkinter` (UI)
- `matplotlib` (gráfico)
- `requests` (HTTP)
- `gdeltdoc` (GDELT)
- `python-dateutil` (parse de datas)

---

## 2) Instalação

Na pasta do projeto:

```bash
pip install -r requirements.txt
```

---

## 3) Chaves de API (recomendado)

Para notícias melhores e mais rápidas, configure:

- Alpha Vantage: variável `ALPHAVANTAGE_API_KEY`
- Finnhub: variável `FINNHUB_API_KEY`

### Windows (PowerShell)

```powershell
setx ALPHAVANTAGE_API_KEY "SUA_CHAVE"
setx FINNHUB_API_KEY "SUA_CHAVE"
```

Depois **feche e reabra** o terminal/PyCharm para carregar as variáveis.

> **GDELT não precisa de chave**.

---

## 4) Como executar (abre a janela)

### Opção A — Entry point (mais simples)
```bash
python main.py
```

### Opção B — Módulo Python
```bash
python -m trading_assistant
```

Ao abrir:
1. Clique **Iniciar**
2. Selecione o **Ativo**
3. Veja **candles**, **book**, **notícias**, **NewsImpact** e **recomendação**
4. Use BUY/SELL (paper) com **dupla confirmação**

---

## 5) O que está “real” e o que está “mock”

### Mock (por enquanto)
- Market data (candles) — gerado em `data_feeds/market_stream.py`
- Book/ladder — gerado no pipeline (mock)

### Real (já funcional)
- **Notícias**:
  - Alpha Vantage (NEWS_SENTIMENT)
  - Finnhub (general news)
  - GDELT (global coverage via `gdeltdoc`)
- **NewsImpactScore** por ativo (com decaimento e mapeamento keyword→ativo)
- **Gestão de risco** e validações básicas
- **Execução Paper** (simulada com slippage simples)

---

## 6) Estrutura do projeto

```
PULSE-TRADER/
  main.py
  requirements.txt
  README.md
  trading_assistant/
    __init__.py
    __main__.py
    config.py
    app.py
    core/
      models.py
      state.py
    data_feeds/
      market_stream.py
      news_stream.py
      news_sources/
        alpha_vantage.py
        finnhub_client.py
        gdelt_client.py
    news_impact/
      scorer.py
    signals/
      technicals.py
      engine.py
    risk/
      risk_engine.py
      validator.py
    execution/
      order_router.py
    alerts/
      notifier.py
    infra/
      audit.py
    ui/
      dashboard.py
```

---

## 7) Configurações principais

Você pode ajustar as configs em `trading_assistant/config.py`:

- Ativos exibidos:
  - `MarketFeedConfig.symbols`
- Frequência do mock market:
  - `MarketFeedConfig.timeframe_seconds`
- Keywords e mapeamento keyword→ativo:
  - `NewsFeedConfig.keywords`
  - `NewsFeedConfig.keyword_to_symbols`
- Risco:
  - `RiskConfig.capital`
  - `RiskConfig.risk_per_trade`
  - `RiskConfig.max_daily_loss`
  - `RiskConfig.max_trades_per_day`
- Validações:
  - `ValidatorConfig.max_spread`
  - `ValidatorConfig.max_news_impact`

---

## 8) Roadmap (próximos passos)

1) **Trocar market mock por feed real**
   - Profit Pro (primeiro só leitura: candles/book/negócios)
2) Book real + filtro de liquidez/spread
3) Painel de “Plano do Trade”
   - Entrada/Stop/Alvos + risco R$ + margem estimada
4) Backtest / replay + relatório de performance
5) Conectar execução real (Profit) com controles:
   - dupla confirmação + “kill switch” + limites diários

---

## 9) Aviso legal

Este software é para **apoio à decisão** e estudo.
Operar em mercados envolve risco e pode gerar perdas.
Você é responsável por qualquer operação realizada.

---

## Suporte / evolução

Se quiser deixar a UI ainda mais “igual Profit Pro”:
- watchlist com semáforo (BUY/SELL/WAIT) por ativo
- heatmap de impacto de notícias
- ranking de oportunidades
- painel de posições e PnL em tempo real (paper)
