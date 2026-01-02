# PULSE-TRADER

Dashboard estilo *Profit* + motor de sinais explicável (BUY/SELL/WAIT) com **shadow trading** (paper automático), **stops curtos + alvos longos**, e **calibração online** baseada na performance.

---

## O que já está implementado

### 1) Redundância inteligente
- Sinal é formado por componentes independentes (tendência, momento, impacto de notícias).
- Cada decisão vem com **reason** (explicação) e **meta** (valores que geraram o sinal).

### 2) Adaptabilidade
- **OnlineCalibrator** ajusta periodicamente parâmetros do motor (threshold, stop ATR, alvo em R) usando a performance do shadow trading.

### 3) Transparência
- Cada sinal mostra: tendência (EMA), momento (em ATR), penalidade de notícia e score final.
- Dashboard mostra **Confiança** (em %) e desempenho (Win rate / Avg R).

### 4) Robustez
- Funciona em múltiplos símbolos e timeframes (em simulação/mock).
- Mock agora gera candles em **regimes** (trend/lateral/vol), para o motor treinar sem “saber o futuro”.

### 5) Gestão de risco avançada
- Stops e targets automáticos (baseados em ATR).
- Position sizing por risco (opção “Risco” na UI).

### 6) Validação contínua
- **Shadow trading** abre/fecha operações automaticamente (paper) e mede:
  - trades, win rate, avg R, profit factor, drawdown em R
- Script de treino sintético roda milhares de velas para testar e calibrar sem dados externos.

---

## Como rodar

### 1) Criar e ativar venv
```bash
python -m venv .venv
source .venv/bin/activate  # mac/linux
# .venv\Scripts\activate  # windows
```

### 2) Instalar dependências
```bash
pip install -r requirements.txt
```

### 3) Abrir o app
```bash
python main.py
```

---

## Dashboard (UI)

### Recursos principais
- **Tela cheia (windowed)** por padrão (ocupa o monitor inteiro)
  - `F11` volta para tela cheia
  - `ESC` volta tamanho padrão
- **Escala vertical fixa tipo Profit**
  - Escala: `Fixa (Profit)` ou `Auto`
  - Faixa: define quantos “pontos/preço” a escala fixa exibe (ex.: 200)
  - Tem um “respiro” extra para não cortar os pontos/linhas
- **Seguir**
  - Quando ligado, o gráfico acompanha as últimas velas (ao vivo)
  - Quando desligado, você pode pan (◀ ▶) para olhar o histórico
- **Livro de ofertas**
  - Mostra **8 níveis** (para sobrar espaço na área de Ordem)
- **Linhas de orientação no gráfico**
  - Entrada: ciano
  - Stop: vermelho
  - Alvo: verde
- **Cores de linhas na tabela**
  - Compra = verde
  - Venda = vermelho
  - Esperar = azul claro

### “Para que serve o botão Seguir?”
- Mantém o gráfico no “ao vivo” (sempre mostrando as últimas velas).
- Se você quiser olhar o histórico, desligue “Seguir” e use ◀ ▶.

### “Quantos pontos o gráfico abrange? E se variar 80 pontos?”
- Em **Escala Fixa (Profit)**, o gráfico sempre mostra uma faixa vertical fixa definida em **Faixa** (ex.: 200).
- Se o preço variar 80 pontos, ele continua aparecendo normalmente **desde que esteja dentro da faixa**.
- Se estourar, aumente “Faixa” (ex.: 300 / 400).

---

## Motor de sinais (stops curtos + alvos longos)

Arquivo: `trading_assistant/signals/engine.py`

- Tendência: EMA rápida vs EMA lenta
- Momento: distância do preço para EMA lenta em unidades de ATR
- Penalidade: notícias fortes reduzem a chance de operar

Stops e targets:
- `stop_dist = stop_atr_mult * ATR`
- `target_dist = stop_dist * reward_r`

Config padrão:
- `stop_atr_mult = 0.70` (stop curto)
- `reward_r = 3.00` (alvo longo)
- `min_confidence = 0.55` (evita sinal fraco)

---

## Shadow Trading (paper automático)

Arquivo: `trading_assistant/validation/performance.py`

- Abre 1 trade por símbolo quando chega BUY/SELL (confiança mínima).
- Fecha em TP/SL usando OHLC (conservador se tocar TP e SL no mesmo candle → conta SL).
- Fecha por tempo se passar de X candles.
- Envia eventos para a UI:
  - `shadow_position` (desenha linhas no gráfico)
  - `shadow_trade` (quando fecha)
  - `performance` (snapshot)

---

## Calibração Online

Arquivo: `trading_assistant/validation/calibrator.py`

- A cada N trades fechados, ajusta levemente:
  - `threshold` (seletividade)
  - `stop_atr_mult` (largura do stop)
  - `reward_r` (alvo em R)
- Sempre com limites (clamp) para evitar “explodir” parâmetros.

---

## Treino sintético (sem dados externos)

Arquivo: `trading_assistant/validation/train_synthetic.py`

Roda milhares de candles sintéticos em regimes e mede performance do motor.

Exemplo:
```bash
python -m trading_assistant.validation.train_synthetic --symbol WIN --steps 20000 --tf 5
```

---

## Estrutura de pastas (principal)

```
PULSE-TRADER/
  main.py
  requirements.txt
  trading_assistant/
    app.py
    config.py
    core/
      models.py
      state.py
    data_feeds/
      market_stream.py
    signals/
      engine.py
      technicals.py
    risk/
      risk_engine.py
    ui/
      dashboard.py
    validation/
      performance.py
      calibrator.py
      train_synthetic.py
```

---

## Avisos importantes

- **Modo Real** na UI é o modo para plugar execução real (corretora/Profit/API).  
  Neste repositório, a execução real depende da integração que você escolher (Profit, corretora, API etc.).
- O **motor é explicável e calibrável**, mas não é “garantia” de lucro.  
  Use o shadow trading para validar e só depois pense em execução real.

