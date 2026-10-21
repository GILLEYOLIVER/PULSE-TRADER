# Experimento de confirmação por prazo maior

## Hipótese e momento de aplicação

Entradas de um prazo curto podem contrariar uma tendência mais longa. O experimento compara a grade anterior com variantes que exigem confirmação em candles de duração cinco vezes maior. Não há vantagem financeira comprovada. A rodada `20261021T043007572293` continua executando sua cópia congelada anterior; nenhuma escolha ou janela já aberta é alterada.

## Regras fixadas antes dos novos externos

- A grade de cinco minutos e uma hora passa a incluir `multi_timeframe=False/True`, mantendo os métodos, filtros, alvos e stops anteriores. A sequência completa tem 420 combinações predefinidas; cada rodada continua limitada ao número informado de candidatas. A permutação e rotação são determinísticas. A grade diária permanece sem essa ampliação porque seus primeiros blocos não contêm 200 candles do prazo maior.
- Tendência, rompimento, pullback e adaptativo usam o alinhamento EMA9/21 já implementado no prazo maior. Os métodos de médias mantêm sua confirmação já existente.
- O método de retorno à média passa a respeitar o indicador multitemporal, antes ignorado por esse método: SMA50 acima/abaixo da SMA200 no prazo maior e o último fechamento desse prazo no mesmo lado da SMA200. Sem os 200 candles maiores encerrados, aguarda.
- O agrupamento usa somente buckets completos, contíguos e encerrados. Um candle maior em formação não fornece seu fechamento, mesmo quando alguns de seus candles menores já são conhecidos. Não há preenchimento de lacunas.
- Apenas SMA e retorno à média com confirmação multitemporal precisam reter 1.024 candles base; as outras configurações mantêm o limite de 1.000. Esse espaço inclui as bordas incompletas do agrupamento e evita que 1.000 barras armazenadas produzam somente 199 barras maiores.
- O contexto externo dos próximos lotes passa a exigir 1.024 candles anteriores para ambos os lados da comparação. As referências antigas continuam truncando/interpretando esses mesmos dados segundo seu código original. O desenvolvimento recebe até 1.024 candles anteriores a cada bloco, nunca dados posteriores; insuficiência de contexto ou operações não é suprida com dados futuros.
- Nenhum orçamento de risco, taxa, stop, alvo ou gate financeiro foi relaxado. O filtro pode apenas impedir uma proposta; não muda os níveis da proposta original. A grade continua selecionada somente no desenvolvimento. A referência original e uma única candidata congelada passam depois por avaliação externa e custos dobrados.

## Evidência necessária

Os testes mecânicos verificam bloqueio de tendência contrária, funcionamento em ambas as direções, preservação de entrada/stop/alvo, janela maior incompleta sem acesso ao futuro, armazenamento suficiente e ausência de ordens no aquecimento. Isso não mede acerto de mercado.

Ensaios sobre históricos já conhecidos ficam identificados como regressão/desenvolvimento e não qualificam a meta. Só períodos posteriores ainda não reservados poderão fornecer novas confirmações. Todas as perdas, abstenções e encerramentos de fim de janela permanecem no resultado financeiro. As exigências de amostra, lucro, stress, perdas e mais de 90% por janela permanecem as do protocolo principal.

## Primeiro ensaio em desenvolvimento conhecido

O histórico BTCUSDT de cinco minutos de 27/01 a 26/02/2018, já usado antes, foi avaliado nos mesmos três blocos, com alvo fixado em 1,25 R, stop de 1,5 ATR e contexto anterior ampliado. Não houve ajuste dos parâmetros entre os pares. Os oito resultados ficaram inelegíveis por inconsistência financeira:

| Método | Operações sem/com confirmação | Acerto sem/com | Líquido USDT sem/com |
|---|---:|---:|---:|
| Tendência | 234 / 165 | 47,44% / 47,27% | -2.747,37 / -1.860,10 |
| Adaptativo | 140 / 102 | 45,00% / 44,12% | -2.057,25 / -1.587,49 |
| Retomada EMA | 113 / 88 | 44,25% / 43,18% | -861,96 / -818,90 |
| Retorno à média | 73 / 58 | 56,16% / 56,90% | -782,14 / -642,52 |

O filtro reduziu operações e, nesse conjunto, perdas líquidas, mas não produziu uma política lucrativa nem um aumento consistente do acerto. Nenhuma versão foi promovida. Os dados, fontes, protocolo, métricas e relatório estão preservados também no arquivo `runtime/aprendizado/ciclos/runs/multi-timeframe-regression-20261021T044352.zip`. Esse ensaio não entra nas confirmações externas.

Referência metodológica consultada: [Freqtrade: combinação segura de candles de prazos diferentes](https://www.freqtrade.io/en/stable/strategy-customization/#merge_informative_pair). A documentação destaca que timestamps de abertura não tornam disponível antecipadamente o fechamento do prazo maior. A implementação do PULSE usa seu próprio agregador de buckets completos; não instala nem copia o framework.
