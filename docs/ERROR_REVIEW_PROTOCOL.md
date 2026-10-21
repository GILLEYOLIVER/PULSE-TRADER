# Entender perdas e testar correções

## Evidência observada

A explicação posterior do ensaio conhecido `ma-context-regression/20261021T103626` repetiu
seis replays já avaliados, com os modelos congelados, sem rede, sem novos ajustes e sem externo.
Todos os resultados ficaram exatamente iguais aos originais. Na variante por risco inicial,
corte 0,65, o esquema anterior teve 38 vitórias em 54 operações:

- Ganho líquido médio de 34,42 USDT e perda média de 83,50 USDT nas 16 operações não lucrativas.
- Resultado bruto de 550,82 USDT, já com spread/slippage; comissões de 579,06; líquido de -28,25.
- 38 alvos, 15 stops e um encerramento de fim de janela, incluído nas finanças.
- O contexto novo teve 34 vitórias em 51 operações e líquido de -221,87. Ficou preservado como
  experimento optativo; o esquema anterior continua como padrão.

Isso identifica o efeito aritmético dos custos e do tamanho dos ganhos/perdas. Não demonstra
que uma média específica causou cada stop ou que uma alteração de alvo resolverá o problema.
Entradas completas, saídas, sinais e as seis reconciliações estão em `explanations/` no ensaio.

## Rotina das próximas fontes

Cada replay passa a registrar um diagnóstico após os encerramentos: quantidade, ganhos/perdas,
médias líquidas, custos, ponto de equilíbrio descritivo, saídas por motivo, gaps adversos no stop,
perdas acima do orçamento e agrupamento pelo regime registrado. Todos os resultados, inclusive
gaps, perdas e encerramentos forçados, são conservados. Contabilidade inconsistente ou operação
duplicada é recusada. Esses campos não entram nas características usadas antes da entrada.

O ponto de equilíbrio usa as médias observadas da própria amostra; não é taxa de acerto futura.
Zero operações não recebe 100%. Poucas operações ficam descritas sem priorizar novas tentativas.

Somente os diagnósticos dos blocos de **desenvolvimento** da candidata previamente selecionada
podem priorizar experimentos do próximo lote. O teste externo continua como confirmação/rejeição;
seus resultados não alimentam a seleção desses experimentos nem provocam repetição da janela.

São declaradas duas hipóteses, com pelo menos 30 operações em um bloco diagnóstico:

1. Comissões anulam o bruto ou acerto fica abaixo do equilíbrio líquido observado: comparar
   alvos de 1,25R e 2R na mesma base técnica, sujeitos ao risco e custos existentes.
2. Resultado bruto não positivo: comparar a configuração intermediária de seletividade já
   existente (separação de médias 0,35ATR, eficiência 0,20, volume 0,80, distância máxima 1,5ATR
   e confirmação da inclinação). Isso é uma hipótese de entrada, não diagnóstico causal provado.

Esses parâmetros já pertencem à grade técnica declarada. As propostas ocupam posições dentro
do mesmo máximo de candidatas, sem ampliar a busca; referência e padrão ficam preservados.
O conjunto completo e a origem do diagnóstico ficam congelados **antes dos dados do próximo lote**.
O registro contém rodada de origem, candidata, corte e hashes do desenvolvimento/diagnóstico.
As revisões também acompanham as matrizes na memória local de validação com sua cadeia de hashes.
Referências com modelo não transferem o modelo antigo a parâmetros alterados: a proposta técnica
perde o filtro antigo e precisa passar por todo o treinamento/validação novamente.

Uma hipótese só passa a referência após os mesmos gates de desenvolvimento, amostra, caixa,
custos dobrados e externo inédito. Não se modifica código, stop ou alvo de uma rodada já aberta.
Gaps não autorizam aumentar o orçamento ou ocultar a perda. Um erro mecânico requer reprodução,
correção e regressão; uma ideia que perde fica registrada como rejeitada.

A rodada aberta `20261021T104605658546` continua no seu código original, sem esse mecanismo.
Seu protocolo, modelos e resultados não são reescritos. A aplicação é apenas nas próximas fontes.
