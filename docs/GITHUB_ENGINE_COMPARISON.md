# Referências do GitHub e decisões para o PULSE

Pesquisa em 20/10/2026. Foram consultados repositórios e documentação dos mantenedores.
As conclusões de aplicação ao PULSE são análise nossa; não executamos nem comparamos a
rentabilidade desses projetos. Implementação própria, sem importar código ou modelos externos.

| Projeto | Como é construído e analisa | Aplicação nesta iteração |
|---|---|---|
| [Freqtrade / FreqAI](https://github.com/freqtrade/freqtrade) | Candles/indicadores, estratégias, backtest, treino por janelas, armazenamento de modelos e previsões | Teste de prefixos para procurar vazamento de futuro; artefatos com versão; memória separada da avaliação cega |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | Motor por eventos; modelos distintos para preenchimento, taxas, slippage e risco | Custos proporcionais ao financeiro, restrição de venda descoberta e unidades/volume explícitos |
| [Microsoft Qlib](https://github.com/microsoft/qlib) | Pipeline de dados, features, modelos, carteiras e avaliação; separação de períodos para ajustar, validar e testar | Features de regime e fluxo do candle; artefatos com esquema e corte temporal; comparação com modelo simples |
| [PyBroker](https://github.com/edtechre/pybroker) | Indicadores/modelos em cache, NumPy/Numba, paralelismo, walk-forward e estatísticas bootstrap | Retirada de I/O do backtest descartável, tarefas independentes em processos e janelas sucessivas |

## Fontes específicas verificadas

- [Freqtrade: análise de lookahead](https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md):
  compara execuções para procurar alterações causadas por acesso indevido a candles futuros.
- [FreqAI: janelas, modelos e aprendizado contínuo](https://github.com/freqtrade/freqtrade/blob/develop/docs/freqai-running.md):
  retreino temporal, reutilização de modelos e alerta sobre overfitting no aprendizado contínuo.
- [LEAN: modelo de preenchimento](https://github.com/QuantConnect/Lean/blob/master/Common/Orders/Fills/FillModel.cs):
  integração entre eventos de ordem e modelos de slippage/preenchimento.
- [Qlib: benchmark Alpha158/LightGBM](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml):
  períodos distintos de treino/validação/teste e custos de abertura/fechamento.
- [PyBroker: documentação no repositório](https://github.com/edtechre/pybroker): cache, processamento paralelo,
  treinamento temporal e avaliação. Sua licença menciona Apache com Commons Clause; o Freqtrade usa GPL.
  Nenhuma dessas dependências foi incorporada ao PULSE MIT.

## Escolhas

Aumento de complexidade limitado a um candidato adaptativo explicável e um modelo opcional de
14 features. O modelo anterior continua legível. O candidato verifica tendência, eficiência do
movimento, volatilidade, volume e fluxo quando disponível; pode aguardar em vez de negociar.
Custos líquidos e risco são aprovados por uma camada externa ao sinal.

Redes profundas e reinforcement learning não foram adotados nesta rodada: o gargalo medido
estava na serialização do backtest, e os estudos anteriores ainda têm limitações de custos/unidades.
Mais capacidade de modelo exige evidência nova em avaliação externa e não será promovida por
um resultado isolado positivo.
