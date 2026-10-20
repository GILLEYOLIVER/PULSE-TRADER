# PULSE-TRADER 2.0

Plataforma desktop de análise, replay histórico, backtesting e **operações exclusivamente simuladas (PAPER)**.
Não conecta sua conta Rico e não contém envio real de ordens.

## Iniciar no Windows

Requer Python 3.11+ com Tcl/Tk. Na pasta do projeto:

```powershell
python main.py
# ou clique em iniciar.cmd
```

O núcleo, os gráficos Canvas, o replay, o simulador e o backtest usam a biblioteca padrão.
CustomTkinter é usado como janela quando instalado; Tkinter é o fallback testado.
Para ambiente virtual e bibliotecas opcionais da interface anterior:

```powershell
.\scripts\install.ps1
.\scripts\install.ps1 -Full
.\scripts\start.ps1
```

Não é preciso instalar bibliotecas extras para testar a versão nova. A opção `-Full` precisa de internet.
`PULSE_DATA_DIR` define a pasta dos bancos locais (padrão `runtime`). `.env.example` é uma referência;
o programa lê variáveis do processo, sem carregar `.env` automaticamente.

## Usar

1. Abra o aplicativo. A barra indica PAPER e a origem dos dados.
2. Escolha o ativo e **Carregar simulação**, ou use **Importar CSV**.
3. Em **Risco, custos e estratégias**, edite os valores JSON e clique em **Validar e aplicar**.
   `risk_fraction: 0.005` significa 0,5%. Perdas e meta são valores monetários.
4. Clique em **Iniciar** ou **Próximo candle**. A geração de sinais requer 35 candles fechados.
5. A execução automática e os botões manuais passam pelo mesmo motor de risco.
6. A emergência cancela entradas pendentes e bloqueia novas entradas. Stops existentes continuam;
   **Zerar posições PAPER** encerra as posições ao último preço simulado com custos.
7. Exporte JSON na aba de resultados. Fechar a janela preserva posições, ordens e bloqueios.

O gráfico mostra candles, volume, EMA9/EMA21 e níveis das posições; há zoom, navegação,
três timeframes e temas claro/escuro. Indicadores adicionais aparecem nos sinais e no motor.
Não há cotações em tempo real nem livro real conectado. Dados sintéticos não medem rentabilidade real.

## Histórico CSV

```csv
symbol,ts,open,high,low,close,volume,source,seconds
WIN,2026-01-05T12:00:00+00:00,130000,130050,129980,130020,1000,USER_LICENSED_EXPORT,60
```

Informe a origem verdadeira e use somente dados que você tem autorização para utilizar.
O timestamp representa a abertura de um candle **já encerrado**. Fuso é obrigatório.
Valores inválidos, duplicatas e períodos sobrepostos são rejeitados. A agregação omite buckets incompletos.
Use uma série por ativo por execução de backtest. Na UI, a troca de série exige posições encerradas;
o mesmo ledger não pode voltar no tempo. Para um experimento independente, escolha outro `PULSE_DATA_DIR`
sem apagar o estado anterior. Nunca use isso para representar limites de uma conta real.

WIN, WDO, IND, DOL, PETR4 e VALE3 têm especificações iniciais. BTC/ETH representam séries spot em BRL
fornecidas pelo usuário; conversão de USD e derivativos cripto não são implementados.
Os símbolos raiz de futuros são apenas identificação da série importada, sem rolagem automática.
O domínio aceita `Instrument` com vencimento explícito; confira os contratos e o calendário do seu arquivo.

## Linha de comando

```powershell
python -m trading_assistant.v2.cli demo --bars 1000 --seed 42 --output reports/demo.json
python -m trading_assistant.v2.cli backtest --csv historico.csv --strategy trend --output reports/historico.json
python -m trading_assistant.v2.cli walk-forward --bars 600 --output reports/walk-forward.json
python -m trading_assistant.v2.cli sensitivity --bars 300 --output reports/sensitivity.json
python -m trading_assistant.v2.cli train --bars 300 --output reports/model.json
python -m trading_assistant.v2.cli diagnose
python -m unittest discover -s tests -v
python -m scripts.smoke_gui
```

Estratégias: tendência, rompimento e pullback. A análise usa EMA/SMA, RSI, MACD, ATR, VWAP de sessão,
Bollinger, suportes/resistências, momentum, volume relativo, consolidação e volatilidade.
O filtro multitemporal é opcional na configuração da estratégia.
Não há confiança estatística calibrada: o campo fica indisponível, sem porcentagens inventadas.

## Risco e execução

O tamanho considera valor por ponto, lote, stop, custos, margem simulada, exposição e saldo.
Não força um contrato quando o orçamento é insuficiente. Limites diário/semanal/mensal, meta,
quantidade de operações, posições, ativos, estratégias, horário, spread, slippage e cooldown são configuráveis.
As decisões, fills, posições, cancelamentos e bloqueios são gravados em transações SQLite.
Entradas são no próximo candle, com latência configurável e liquidez estimada pelo **volume anterior**.
Preenchimento parcial usa IOC: o restante é cancelado. Stops com gaps usam o pior preço de abertura;
se stop e alvo forem tocados no mesmo candle, considera stop primeiro. Trailing e break-even são opcionais.

## Limites desta entrega

- Rico/Profit: fronteira bloqueada; falta confirmar habilitação, licença, SDK e ambiente autorizado.
- Sem feed B3 em tempo real, calendário oficial carregado, rolagem automática, leilões ou simulação de fila.
- Backtest por um ativo; portfólio multativo sincronizado ainda não implementado.
- Taxas/margens são entradas de simulação, sem tributação ou ajuste diário completo de futuros.
- ML opcional simples, com validação temporal e baselines; não foi validado para operar mercados.
- Bibliotecas gráficas extras e empacotamento `.exe` não puderam ser instalados neste ambiente sem DNS.
- Interface Tk foi exercitada no Windows; o caminho CustomTkinter requer validação com a dependência instalada.
- Módulos anteriores permanecem para estudo, notícias e compatibilidade. Seu roteador de ordens foi desativado
  para impedir que contornem o ledger novo. A entrada `python -m trading_assistant` abre a versão nova.

Veja `docs/ARCHITECTURE.md`, `docs/RISK_MANAGEMENT.md`, `docs/INTEGRATIONS.md`,
`docs/TESTING.md`, `docs/SECURITY.md` e `docs/DELIVERY_REPORT.md`.
