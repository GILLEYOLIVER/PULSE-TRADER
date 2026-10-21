# Menos trabalho repetido por candle

## Perfil observado

Um perfil de 3.000 candles BTC já conhecidos encontrou 2.638.917 chamadas da chave de ordenação
de ordens em `on_bars`. A ordenação recebia todo o histórico, inclusive ordens rejeitadas e encerradas,
embora somente ordens `NEW` pudessem executar. A soma de resultados também convertia repetidamente
os mesmos horários de encerramento para datas e períodos locais.

O motor agora filtra ordens `NEW` antes de ordenar, mantendo a mesma ordem por ativo/identificador.
Um cache limitado a 8.192 entradas guarda somente a conversão pura de um horário para dia/semana/mês.
Saldos, resultados, bloqueios e posições continuam sendo calculados a partir do estado atual.
Nenhum stop, preço, taxa, limite, dado ou critério financeiro é alterado por esta otimização.

## Comparação verificada em 2026-10-21

Foram executados processos Python isolados nas fontes preservadas anterior e otimizada, com os
mesmos 3.000 candles conhecidos, estratégia, custos, capital e captura de características.
Os quatro processos seguiram a ordem anterior/nova/nova/anterior para reduzir efeito da ordem.

| Fonte | Tempos de replay (s) | Mediana (s) |
| --- | --- | ---: |
| Anterior | 8,2711 / 8,8874 | 8,5793 |
| Otimizada | 4,2317 / 4,2251 | 4,2284 |

Nesse ensaio, a vazão foi 2,029 vezes maior e o tempo de replay caiu 50,71%.
Outras pesquisas estavam ativas na máquina; o resultado não garante a mesma melhoria em outro
hardware, tamanho de histórico, estratégia, rede ou no lote completo.

Todos os quatro hashes financeiros foram exatamente
`69843583ae6787b7c6ad0b0b236e6b59ddf5f89dab284dc212709941eec36f4c`.
O conteúdo verificado inclui métricas, 1.794 ordens, 130 operações, curva de patrimônio e
129 rótulos naturais com suas características e risco inicial. Nada foi comparado apenas por acerto arredondado.

Dados, executores, tempos, fontes e perfil ficam em
`reports/initial-risk-regression/20261021T065000/`, especialmente
`replay-overhead-benchmark.json` e `teacher-3000-before-profile.json`.
Este é um teste de mecânica e processamento em histórico conhecido, sem evidência externa nova
ou promoção de algoritmo de negociação. As fontes das rodadas já abertas permanecem intactas.
