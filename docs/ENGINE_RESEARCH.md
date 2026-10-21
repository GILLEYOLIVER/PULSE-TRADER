# Motor: plano de medição e avaliação cega

## Contrato desta iteração

Objetivo: tornar cálculos e pesquisa mais rápidos, corrigir custos e unidades de execução,
e acrescentar decisões que possam abster-se quando não houver evidência. Execução somente PAPER.
Entradas são candles encerrados; nenhuma identificação de cenário, resultado futuro ou rótulo
da avaliação pode ser passado ao motor. O registro explica regras e números, sem atribuir
consciência ou raciocínio humano ao algoritmo.

## Experimentos fixados antes das alterações

1. Medir snapshot e replay em entrada determinística, três medidas de indicadores e perfil de CPU.
   No máximo três variantes de cálculo, sem mudar os parâmetros para obter vantagem de velocidade.
   Preservar resultados do replay legado e indicadores dentro de tolerância numérica.
2. Conferir taxas proporcionais ao financeiro, tamanho da unidade, liquidez e impedimento de venda
   descoberta em um instrumento configurado somente para compras. Zero bps preserva a configuração antiga.
3. Acrescentar um candidato de análise de regime, tendência, ruído e custo. Ele será opcional;
   não substituirá automaticamente a configuração ou o modelo do usuário.
4. Treinar/selecionar apenas no conjunto de desenvolvimento. Congelar parâmetros e hash antes
   da avaliação cega. Usar períodos reais novos e cenários adversos construídos pelo avaliador.
   O teste final não será reutilizado para ajustar parâmetros nesta iteração.

## Evidência e critérios

Registrar SHA do código/dados, parâmetros, separação temporal e falhas por cenário. Medir lucro
líquido simulado, drawdown, operações, custos, sinais recusados, calibração e latência.
Aceitar melhora de desempenho somente com equivalência numérica e testes de correção aprovados.
Condições para considerar uma estratégia candidata: resultado líquido e sob custos maiores positivos,
amostra suficiente, estabilidade em janelas e ativos distintos e ausência de violação de risco.
São filtros de pesquisa, não prova de vantagem nem autorização para ordens reais.

Fontes pesquisadas: endpoints públicos de candles e metadados de negociação da Binance,
arquivos históricos e hashes oficiais; brapi/Mercado Bitcoin já disponíveis. Volume de negócios
e agressão podem acrescentar informação do próprio candle encerrado, sem inventar um livro
de ofertas histórico a partir de OHLC. Dados econômicos diários do BCB têm uso contextual e
precisam respeitar a hora de publicação; não representam cotação negociável de WDO.

Artefatos locais desta execução: `reports/engine-upgrade/`. Nenhuma promoção automática;
rollback por commit e preservação dos modelos/configuração existentes em runtime.
