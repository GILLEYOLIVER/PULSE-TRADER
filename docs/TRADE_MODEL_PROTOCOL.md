# Filtro de entradas por resultados líquidos

A hipótese posterior de [contexto de médias móveis](MA_CONTEXT_PROTOCOL.md) versiona as
características das próximas fontes: 26 medidas, mantendo intactos os modelos anteriores de 18.
Ela preserva os mesmos critérios financeiros e não modifica avaliações já abertas.
O ensaio conhecido não sustentou a substituição: o padrão continua em 18, com 26 disponível
somente para experimentos explicitamente declarados antes de novos dados.

## Hipótese

As regras de médias, tendência e volume produzem muitas entradas perdedoras depois dos custos. O experimento testa um algoritmo estatístico regularizado que aprende quais contextos das propostas anteriores terminaram com lucro líquido. Ele não usa IA generativa e não promete mais de 90% de acerto.

## Dados e tempo

- O professor é o próprio simulador PAPER, com as mesmas taxas, spread, slippage, liquidez, bloqueios, entradas no candle seguinte, stops e alvos.
- As 18 características são registradas quando a proposta é emitida, antes do preenchimento: indicadores de candles encerrados, volume/fluxo disponível, relações de alvo/stop/custos e direção.
- O rótulo só fica disponível quando a operação termina. Entradas duplicadas e rótulos posteriores ao corte de treino são recusados.
- Encerramentos forçados no fim do histórico não têm um desfecho natural conhecido e não entram no ajuste, independentemente do sinal do resultado. Eles continuam integralmente nas métricas financeiras de todas as validações e testes. Nenhuma perda é removida dos resultados.
- Exigem-se 100 operações naturais encerradas, com ao menos 20 lucrativas e 20 não lucrativas, antes de ajustar um modelo. Sem isso, a candidata fica inelegível.

## Seleção antes do teste externo

1. A grade técnica é avaliada em três blocos cronológicos comuns. O contexto anterior inicialmente continha 250 candles; a próxima [iteração multitemporal](MULTI_TIMEFRAME_PROTOCOL.md) passa a usar até 1.024 no desenvolvimento e exigir 1.024 antes do teste externo, sem sinais ou ordens durante o aquecimento. Rodadas anteriores não são modificadas.
2. No máximo duas bases técnicas com amostra entram no experimento de filtro. Sua escolha usa somente o desenvolvimento. Na [iteração de histórico ampliado](LONG_HISTORY_PROTOCOL.md), até seis bases do ranking técnico têm o prefixo anterior ao primeiro bloco verificado; as primeiras duas com amostra suficiente seguem para os quatro limiares. Não há seleção por resultados externos ou relaxamento das contagens.
3. Para cada bloco, o modelo é ajustado novamente com operações encerradas **antes** daquele bloco. Normalização, pesos e amostra vêm somente desse passado.
4. São estudados os limiares fixos 0,55/0,65/0,80/0,90 da pontuação interna. Esses números não são probabilidades calibradas nem porcentagens esperadas de acerto.
5. Uma candidata precisa dos mesmos critérios de quantidade de operações, lucro, perdas e consistência das regras técnicas. Modelos que apenas deixam de operar não ganham acerto de 100%.
6. Se um filtro for escolhido, seu modelo final é ajustado usando apenas o desenvolvimento e congelado antes de baixar a janela externa. A referência e a candidata são avaliadas também com custos dobrados.

Quando a referência já tem um modelo, todas as candidatas usam os mesmos blocos posteriores ao corte desse modelo. Isso impede comparar a referência dentro do próprio período de treinamento ou avaliar versões em períodos diferentes. A referência preservada acumula sua própria confirmação, mesmo quando uma desafiante não é promovida.

## Persistência e limites

Modelos, características/rótulos, cortes temporais e diagnósticos ficam em `trade-models/` dentro de cada relatório e no ZIP correspondente de `runtime/aprendizado/ciclos/runs/`. A configuração congelada e a versão por hash incluem o modelo selecionado. Os dados usados só como regressão são identificados e não contam como janela externa nova.

O modelo é uma regressão logística L2 implementada com a biblioteca padrão. A pontuação é explicitamente não calibrada; nenhuma probabilidade é exposta na decisão. Histórico incompatível, próprio período de treino, checksum incorreto e parâmetros de entrada/stop/alvo diferentes são recusados. Desvio extremo das características provoca abstenção. Custos dobrados mantêm o modelo congelado e mudam a execução, para testar sensibilidade.

Um primeiro ensaio mecânico com desenvolvimento SOLUSDT já conhecido treinou os três blocos com 107, 144 e 151 operações encerradas. Os filtros tiveram duas operações no limiar 0,55 e nenhuma nos mais altos; ficaram inelegíveis. Isso prova a execução do caminho e a rejeição por falta de amostra, sem demonstrar melhoria de negociação.

Esse ensaio também revelou desvios de aproximadamente 10^-14 em características que deveriam ser constantes, como alvo/risco e stop/ATR. A normalização foi corrigida com piso de escala de 10^-6 para não aprender nem amplificar ruído de arredondamento. O ensaio anterior é preservado; a correção é avaliada como regressão antes de novas janelas.

Na repetição com escala corrigida, o limiar 0,55 manteve duas operações e ambas foram negativas; os demais não operaram. A correção numérica foi necessária, mas esse conjunto conhecido não demonstrou vantagem de negociação e não promoveu um filtro.

Os seis testes antigos de uma hora com menos de 250 candles de contexto foram identificados em `runtime/aprendizado/ciclos/audits/`. Seus resultados financeiros e arquivos originais foram preservados; essas execuções não qualificam a meta. A rotina agora dimensiona o contexto pelo período do candle e exige a amostra antes de iniciar a avaliação.

Referência metodológica: [validação temporal do scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html). Não é uma dependência instalada nem uma reprodução do desempenho de outro projeto.
