# Hipótese prospectiva: contexto de médias nos filtros aprendidos

## Diagnóstico e limites

O diagnóstico conhecido de cinco prefixos de professores da rodada `20261021T084803802628`
separou operações por fechamento/SMA50/SMA200 e inclinação da SMA200. Exigir alinhamento não
melhorou uniformemente os resultados: nos prefixos BTC/ETH de cinco minutos houve menos acertos
e pior resultado médio por risco entre as operações alinhadas. Nos horários houve diferenças
favoráveis, sem comprovação externa. Essa separação descritiva não é um backtest de uma nova
estratégia: impedir uma entrada muda as posições e os bloqueios seguintes.

Por isso, a hipótese é fornecer contexto ao filtro aprendido, sem impor um bloqueio universal.
Os diagnósticos originais ficam em `reports/long-ma-diagnostic/20261021T102000/`, com regra
registrada antes do cálculo. Não serão contados como confirmação inédita ou usados para
escolher retrospectivamente quais ativos participam da meta.

## Esquema fixado antes da comparação e de novos externos

O novo esquema `trade_ma_regime_v2` acrescenta oito medidas às 18 anteriores:

1. Distância do fechamento à SMA50, em ATR, no sentido da operação.
2. Distância à SMA200, nas mesmas unidades.
3. Variação da SMA50 em cinco observações encerradas, em ATR e no sentido da operação.
4. Variação da SMA200 nas mesmas condições.
5. RSI de dois períodos, entre zero e um, com suavização de Wilder sobre até 200 variações passadas.
6. ATR dividido pelo fechamento.
7. Disponibilidade das 205 observações necessárias ao contexto completo.
8. Interação entre a inclinação da SMA200 e a distância à SMA50, ambas orientadas pela operação.

São usadas somente observações encerradas até o sinal; informação posterior é recusada.
Médias/inclinações indisponíveis recebem zero e a disponibilidade recebe zero. Nenhuma operação
perdedora é removida por esse motivo. O filtro recebe essa informação e o mesmo gate de drift.
As medidas mantêm o limite numérico de ±50, escala de treino com piso 10^-6 e drift máximo oito.
Não se usa resultado, taxa de acerto ou risco realizado futuro como característica.

Modelos antigos continuam com esquema 1 e exatamente as 18 características anteriores.
Modelos novos têm esquema 2, identificador explícito e 26 características em ordem fixa.
Cache de professor deve conferir também o esquema: não há reaproveitamento silencioso de
vetores incompatíveis. Todas as três variantes financeiras preservam suas unidades e perdas.

## Comparação e adoção

Antes de novos externos, comparar uma base fixa (`trend`, alvo 0,5R, stop 2,5ATR) no desenvolvimento
BTC conhecido de 30/01 a 30/04/2018, nos mesmos três blocos, com os dois esquemas. Cada esquema
tem três modelos e quatro cortes: 24 comparações conhecidas ao todo. Não selecionar outra base
ou alterar características/limiares depois de ver esses resultados para repetir essa avaliação.
Preservar todos os resultados e conferir a equivalência do caminho antigo com a matriz arquivada.
Uma falha mecânica pode ser corrigida e identificada; uma perda financeira não é uma falha mecânica.

Nos lotes posteriores, o esquema novo ocupa o mesmo máximo de **24 variantes aprendidas**:
duas bases, três modelos e quatro cortes. Não duplicar o orçamento de busca adicionando também
24 variantes antigas. Referências antigas continuam executadas no seu próprio código arquivado.
Somente uma candidata é escolhida pelo desenvolvimento e congelada antes do externo.
Risco, custos, quantidade de operações, lucro por bloco, stress e confirmação da meta permanecem
iguais. Nenhuma adoção na interface ou promoção decorre apenas da disponibilidade do esquema.
Se não houver vantagem comprovada, preservar a referência e registrar a rejeição.

A rodada `20261021T084803802628` terminou com seu esquema original de 18 características;
seus modelos, fonte e critérios permanecem imutáveis.

## Correção mecânica antes da comparação financeira

A primeira fonte experimental emparelhou fechamentos incorretamente no RSI2 quando havia menos
de 201 observações. O ensaio parcial `20261021T112000` foi interrompido sem comparação financeira
concluída; sua fonte e os prefixos permanecem preservados. A correção usa diferenças entre
observações adjacentes também nos prefixos curtos, com teste de séries crescentes e decrescentes.
O ensaio substituto `20261021T103626` mantém a mesma base, dados, cortes, características e gates.
Esses identificadores de pastas não determinam a cronologia: os registros de execução preservam
os horários efetivos, inclusive o nome manual da primeira pasta.
