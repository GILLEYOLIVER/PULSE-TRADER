# PULSE-TRADER 2.2

Plataforma desktop de análise, replay histórico, backtesting e **operações exclusivamente simuladas (PAPER)**.
Não conecta sua conta Rico e não contém envio real de ordens.

## Atualização do motor

[Resultados, limites e memória local da versão 2.2](docs/ENGINE_2_2_RESULTS.md).
Inclui pesquisa mais rápida, custos proporcionais, controle de moeda/unidades, métodos por
médias móveis, dados públicos de atividade do candle e estudos com treino e avaliação separados.
As novas estratégias permanecem candidatas: os testes não demonstraram vantagem consistente.
O motor de decisão usa regras locais; modelos estatísticos são opcionais.

A memória fica em `runtime/aprendizado/`, com históricos, modelos e registros separados de
treino e avaliação. Na aba Ajuda há **Abrir memória de aprendizado**. O treino pela interface
preserva automaticamente seu histórico nessa pasta. Não precisa instalar banco ou servidor.

`python -m scripts.research_goals --plan-only` mostra janelas inéditas; sem `--plan-only`,
executa duas rodadas limitadas em períodos móveis, com dois processos de CPU por padrão.
Cada ciclo preserva seus relatórios. A memória pode propor parâmetros do treino anterior;
os resultados cegos ficam fora dessa seleção.

## Rotina de pesquisa e comparação de versões

A nova rotina está descrita em [Ciclo de pesquisa](docs/CONTINUOUS_RESEARCH.md).
Ela preserva código e configurações, compara cada ativo/prazo separadamente, avança
cronologicamente pelos históricos e mantém a referência quando a candidata não passa.
As comparações externas executam a referência com seu código e regras originais em
processo isolado; uma atualização de código não substitui a melhor versão por si só.
Há filtros de entrada por médias, direção, volume e afastamento, um candidato de retorno
à média e testes com custos dobrados. A meta de mais de 90% ainda depende de confirmação;
nenhuma porcentagem é garantida. A execução continua exclusivamente PAPER.

O experimento de [aprendizado com operações encerradas](docs/TRADE_MODEL_PROTOCOL.md)
usa resultados líquidos anteriores para filtrar entradas. Ele tem cortes temporais,
amostra mínima e validação posterior; sua pontuação interna não é probabilidade de acerto.

```powershell
.\.venv\Scripts\python.exe -m scripts.research_cycle --plan-only
.\.venv\Scripts\python.exe -u -m scripts.research_cycle --cycles 1 --workers 2 --candidates 36
```

O assistente tem uma continuidade a cada duas horas para esta pesquisa. Por regra do
usuário, ela deve interromper a tarefa quando restarem **40% ou menos da cota semanal
do Codex**, preservando os resultados. O executável não acessa a conta Codex.

## Iniciar no Windows

Requer Python 3.11+ com Tcl/Tk. Na pasta do projeto:

### Abrir com F5 no VS Code

Abra **esta pasta `PR-TR`** no VS Code (Arquivo > Abrir Pasta), instale as extensões
Python e Python Debugger quando o VS Code oferecer e pressione **F5**. A configuração
`PULSE-TRADER (PAPER)` abre `main.py` com a pasta correta de trabalho, para manter o
estado simulado em `runtime/` dentro deste projeto. Se o ambiente `.venv` ainda não
existir, execute `powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1` no terminal
do VS Code e tente F5 novamente. Use **Shift+F5** para encerrar a janela do depurador.

### Abrir pelo terminal ou atalho

```powershell
python main.py
# ou clique em iniciar.cmd
```

O núcleo, os gráficos Canvas, o replay, o simulador e o backtest usam a biblioteca padrão.
CustomTkinter é usado como janela quando instalado; Tkinter é o fallback. Ambos foram testados no Windows.
Pillow, incluído em `install.ps1 -Full`, desenha candles e médias móveis em resolução
dobrada com antialiasing. Sem ele, as médias também são suavizadas pelo renderizador
interno e o Canvas do Tkinter continua disponível.
No Windows, a janela usa a escala DPI do monitor; maximize a janela para obter
mais espaço para candles e eixos. Mais pixels melhoram a nitidez, mas não criam
informações de mercado além das que existem no CSV ou na simulação.
Para ambiente virtual e bibliotecas opcionais da interface anterior:

```powershell
.\scripts\install.ps1
.\scripts\install.ps1 -Ui   # apenas CustomTkinter e Pillow
.\scripts\install.ps1 -Full
.\scripts\start.ps1
```

Não é preciso instalar bibliotecas extras para testar a versão nova. `-Ui` instala apenas as bibliotecas
da interface; `-Full` instala também as dependências opcionais legadas. Ambas precisam de internet.
`PULSE_DATA_DIR` define a pasta dos bancos locais (padrão `runtime`). `.env.example` é uma referência;
o programa lê variáveis do processo, sem carregar `.env` automaticamente.

## Usar

O upgrade 2.1 inclui fontes públicas, conversão do Profit, validação temporal, contexto de empresas,
planos vinculados ao replay, formulários completos e backup portátil. [Guia dos seis passos](docs/UPGRADE_6_STEPS.md).

Para usar o executável já construído nesta cópia, abra **iniciar-portatil.cmd**. Ele usa a mesma pasta
`runtime` do projeto. O ZIP portátil pode ser copiado inteiro para outra pasta; seu executável usa
`runtime` ao lado dele. Python e SQLite estão incluídos no pacote; não há servidor de banco a instalar.

1. Abra o aplicativo. A barra indica PAPER e a origem dos dados.
2. Escolha o ativo e **Carregar simulação**, ou use **Importar CSV**.
3. Em **Risco e estratégias**, ajuste capital, risco por operação, perda diária,
   quantidades e estratégia nos controles principais; clique em **Aplicar controles principais**.
   Para outros limites, custos e horários, edite o JSON e clique em **Validar e aplicar configuração**.
   No formulário, `0,5` significa 0,5%; no JSON, `risk_fraction: 0.005` significa 0,5%.
   Perdas e meta são valores monetários simulados.
4. Clique em **Iniciar** ou **Próximo candle**. A geração de sinais requer 35 candles fechados.
5. A execução automática e os botões manuais passam pelo mesmo motor de risco.
6. A emergência cancela entradas pendentes e bloqueia novas entradas. Stops existentes continuam;
   **Zerar posições PAPER** encerra as posições ao último preço simulado com custos.
7. Exporte JSON na aba de resultados. Fechar a janela preserva posições, ordens e bloqueios.
8. Com um CSV histórico autorizado de pelo menos 200 candles de um ativo, abra
   **Ordens e resultados > Treinar modelo com CSV**. O arquivo JSON resultante
   mostra acerto em validação e teste, comparado com referências simples; ele
   não envia ordens, não garante rentabilidade e não é ativado automaticamente.
9. Em **Sugestões**, escolha **No dia** ou **Dias e semanas**. Use **Adicionar CSVs** para
   comparar vários ativos, **Usar replay atual** para analisar somente candles já processados ou
   **Exemplo simulado** para conhecer a tela. Setas e cores mostram alta, baixa ou lateralização;
   selecione o ativo para ler o motivo, a condição de entrada, stop e alvo.
   **Guardar plano PAPER** salva uma proposta sem criar uma ordem. [Guia das sugestões](docs/SUGGESTIONS.md).
10. **Fontes e atualização** consulta históricos públicos da brapi (PETR4/VALE3/ITUB4/MGLU3 sem token)
    ou Mercado Bitcoin (BTC/ETH spot BRL), com atualização opcional a cada 60 segundos.
    O mesmo painel converte CSV do Profit com seleção de período e horário de abertura/encerramento.
11. **Levar ao replay** prepara o histórico sem gerar entradas. **Armar entrada PAPER** verifica a
    identidade dos dados, configurações e risco. Planos condicionais aguardam confirmação em candle fechado;
    a ordem só pode preencher no candle seguinte. **Cancelar plano** cancela pendências ligadas ao plano.
12. **Validar histórico** executa estudo temporal e custos em segundo plano. Uma estratégia sem evidência
    suficiente não é promovida automaticamente. **Risco e estratégias > Editar todos os parâmetros**
    permite configurar todos os limites, custos, horários, calendário, estratégia e especificações sem JSON.
13. Em **Conexões e ajuda**, crie backups consistentes com o programa aberto e restaure em outra pasta vazia.
    A cópia inclui os bancos e arquivos locais; a restauração verifica hashes e integridade dos bancos.

O gráfico mostra candles, volume, EMA9/EMA21 e níveis das posições; há zoom, navegação,
períodos de **1, 5 e 15 minutos** quando os dados de origem permitem, e temas claro/escuro.
Ao importar candles de 5 minutos, por exemplo, o período de 1 minuto não é oferecido.
O eixo do tempo exibe o horário de Brasília. Dados sintéticos seguem uma sequência
contínua e não representam pregões, feriados ou horários oficiais da B3.
Indicadores adicionais aparecem nos sinais e no motor.
Não há cotações em tempo real nem livro real conectado. Dados sintéticos não medem rentabilidade real.

## Histórico CSV

```csv
symbol,ts,open,high,low,close,volume,source,seconds
WIN,2026-01-05T12:00:00+00:00,130000,130050,129980,130020,1000,USER_LICENSED_EXPORT,60
```

Informe a origem verdadeira e use somente dados que você tem autorização para utilizar.
O timestamp representa a abertura de um candle **já encerrado**. Fuso é obrigatório.
Valores inválidos, duplicatas, períodos sobrepostos e mistura de origem ou duração para o mesmo ativo
são rejeitados. A agregação omite buckets incompletos.
O backtest aceita vários ativos em um CSV quando há exatamente um candle de cada ativo em cada intervalo sincronizado.
As entradas usam as aberturas de todos os ativos antes de qualquer máxima, mínima ou fechamento do intervalo.
Walk-forward, sensibilidade, treino e UI continuam com uma série por execução. Na UI, a troca de série exige posições encerradas;
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

### Calendário de sessão opcional

Para bloquear entradas fora de horários e feriados que você conferiu, salve um JSON como este:

```json
{"holidays":["2026-01-01"],"start":"09:00:00","end":"18:00:00","verified":true}
```

No backtest, acrescente `--calendar-json caminho-do-arquivo.json`. Na interface, coloque o mesmo objeto
em `calendar` no JSON avançado e aplique a configuração. `verified` registra sua conferência da lista;
o programa não consulta nem certifica o calendário oficial da B3. Com `calendar: null`, o calendário
opcional não é aplicado. Com `verified: false`, novas entradas de ativos B3 são bloqueadas. Saídas
protetivas PAPER continuam no replay, mesmo fora da sessão. Datas e horários são de São Paulo.
Não altere o calendário enquanto houver posição ou ordem pendente.

Estratégias: tendência, rompimento e pullback. A análise usa EMA/SMA, RSI, MACD, ATR, VWAP de sessão,
Bollinger, suportes/resistências, momentum, volume relativo, consolidação e volatilidade.
O filtro multitemporal é opcional na configuração da estratégia.
Não há confiança estatística calibrada: o campo fica indisponível, sem porcentagens inventadas.

## Risco e execução

O tamanho considera valor por ponto, lote, stop, custos, margem simulada, exposição e saldo.
Não força um contrato quando o orçamento é insuficiente. Limites diário/semanal/mensal, meta,
quantidade de operações, posições, ativos, estratégias, horário, spread, slippage e cooldown são configuráveis.
Quantidades de contratos, operações, horas e latência devem ser números inteiros.
As decisões, fills, posições, cancelamentos e bloqueios são gravados em transações SQLite.
Entradas são no próximo candle, com latência configurável e liquidez estimada pelo **volume anterior**.
Quando faltam candles por mais tempo que o limite de idade dos dados, ordens pendentes daquele ativo
são canceladas antes da próxima abertura; sinais expirados são rejeitados. Stops de posições
existentes continuam sendo avaliados no candle seguinte, com risco de gap.
Preenchimento parcial usa IOC: o restante é cancelado. Stops com gaps usam o pior preço de abertura;
se stop e alvo forem tocados no mesmo candle, considera stop primeiro. Trailing e break-even são opcionais.

## Limites desta entrega

- Rico/Profit: fronteira bloqueada; falta confirmar habilitação, licença, SDK e ambiente autorizado.
- APIs públicas fornecem histórico com referência de data; não são um feed oficial B3 em tempo real. Sem calendário oficial completo, rolagem automática, leilões ou simulação de fila.
- Backtest de portfólio exige candles sincronizados e completos para todos os ativos; não simula horários de negociação distintos.
- Taxas/margens são entradas de simulação, sem tributação ou ajuste diário completo de futuros.
- Modelos passam por treino/validação/teste separados e calibração condicional. Nos quatro estudos reais realizados, nenhum passou pelo filtro de evidência ou calibração.
- `scripts/build.ps1` gera executável e ZIP portáteis, com teste interno offline. Assinatura e homologação em outro computador permanecem externas a esta entrega local.
- Módulos anteriores permanecem para estudo, notícias e compatibilidade. Seu roteador de ordens foi desativado
  para impedir que contornem o ledger novo. A entrada `python -m trading_assistant` abre a versão nova.

Veja `docs/ARCHITECTURE.md`, `docs/RISK_MANAGEMENT.md`, `docs/INTEGRATIONS.md`,
`docs/TESTING.md`, `docs/SECURITY.md` e `docs/DELIVERY_REPORT.md`.
