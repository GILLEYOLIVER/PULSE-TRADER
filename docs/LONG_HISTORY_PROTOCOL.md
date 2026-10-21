# Desenvolvimento com mais histórico e amostra verificada

## Motivo e hipótese

O diagnóstico dos prefixos de treino da rodada `20261021T035539524994` encontrou várias bases abaixo de 100 operações naturais ou de 20 exemplos por classe. Nos prefixos SOL de uma hora havia somente 15 e 20 operações; nos diários examinados, 18 a 53. Outras bases intradiárias tiveram 100 a 214 operações e conseguiram ajustar modelos, mas não comprovaram lucro. Aumentar histórico permite estudar mais situações passadas; não garante melhor previsão.

## Regras para lotes futuros

Antes de abrir novos testes externos, o desenvolvimento passa a abranger:

| Candle | Desenvolvimento anterior | Novo desenvolvimento | Externo |
|---|---:|---:|---:|
| Cinco minutos | 30 dias | 90 dias | 28 dias |
| Uma hora | 365 dias | 540 dias | 90 dias |
| Diário BTC/ETH | 365 dias | 1.460 dias | 90 dias |
| Diário BNB/SOL | 1.460 dias | 1.460 dias | 90 dias |

Os três blocos de validação continuam cronológicos e comuns às candidatas, depois de qualquer corte de um modelo de referência congelado. O contexto anterior continua limitado ao passado. A janela externa não é aumentada depois de observar resultados. Quando necessário, a primeira data elegível avança para comportar o desenvolvimento completo; os períodos incorporados ao treino não poderão ser apresentados depois como avaliação inédita. A rodada `20261021T043007572293`, já aberta, mantém seu código e seus tamanhos anteriores.

## Download, integridade e espaço

Somente a rotina de pesquisa combina partes contíguas de até 10.000 candles, limitadas a 100.000 por conjunto completo. Cada parte mantém paginação do leitor existente, CSV, hashes da resposta/dados, origem, período, lacunas e candles abreviados da fonte. O limite normal da interface não muda. A [documentação oficial da Binance](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data) especifica até 1.000 registros por resposta HTTP e parâmetros temporais em UTC.

As partes são verificadas por mercado, origem, período, limites temporais, ordenação e contagem. O conjunto completo aceita no máximo 5% de candles ausentes, medidos sobre todo o intervalo solicitado. Uma falta localizada não é preenchida nem removida da proveniência. Essa medição usa o mesmo limiar anterior aplicado ao intervalo completo, independentemente do número de partes.

Cada parte concluída tem manifesto com checksum e pode ser reutilizada depois de uma falha. Cache corrompido ou incompleto que se declare concluído causa erro, sem download silencioso para substituir os dados. A leitura de cache verifica todas as partes e o hash agregado. Há conferência de espaço antes de novas transferências; insuficiência preserva o que já foi salvo. Datas futuras são recusadas. Não há consultas a conta, corretora ou ordens.

Grupos com falha também preservam seus arquivos e o motivo no backup de pesquisa, identificados como incompletos. Uma falha não torna o período reservado inédito novamente e não qualifica a meta.

## Elegibilidade do professor antes do ajuste

Após o ranking técnico no desenvolvimento, no máximo seis bases passam por uma verificação de amostra. O professor de cada base recebe somente o prefixo anterior ao primeiro bloco de validação. Conta-se a mesma amostra recente de até 3.000 operações naturais usada pelo ajuste: pelo menos 100, com pelo menos 20 lucrativas e 20 não lucrativas. Nenhum limiar foi reduzido.

As primeiras duas bases desse ranking com amostra suficiente recebem os quatro limiares de pontuação já declarados. Permanecem no máximo oito candidatas aprendidas avaliadas em validação. As bases rejeitadas ficam registradas; não são feitos testes externos extras para escolhê-las. A verificação não escolhe bases por pontuação de modelos ou por resultados externos.

O experimento posterior de [pontuação líquida](NET_SCORE_PROTOCOL.md) acrescenta a segunda variante por base e declara o novo máximo de 16 candidatas aprendidas, sem alterar os critérios financeiros nem as rodadas antigas. A reserva e o adiamento diante de falhas seguem a [recuperação da fonte](PROVIDER_RECOVERY.md).

O primeiro prefixo selecionado é reutilizado sem uma segunda simulação, somente se seu hash de dados, parâmetros e corte temporal forem idênticos. Os modelos dos blocos seguintes continuam ajustados exclusivamente com o passado daquele bloco. Rótulos posteriores ao corte, encerramentos artificiais de fim de janela e dados incompatíveis continuam recusados conforme o protocolo do filtro.

## O que não é conclusão

Mais candles, modelos ajustados ou testes de software passando não demonstram a meta. Promoção e confirmação mantêm as exigências de operações suficientes, lucro líquido, custos dobrados, perdas máximas, mesma versão e janelas externas inéditas. Uma política sem operações não recebe acerto de 100%. Nenhuma versão é adotada na interface por este documento.

## Ensaios em dados conhecidos

O leitor segmentado carregou 25.485 candles BTCUSDT de cinco minutos de 02/01 a 02/04/2018, em três partes. Os 435 candles ausentes dos 25.920 esperados permanecem ausentes e documentados. A releitura integral por cache não fez consultas à rede. Esse período já conhecido foi usado somente como desenvolvimento/regressão.

No prefixo anterior ao primeiro bloco de validação (corte em 16/02/2018 às 18:05 UTC), as amostras naturais foram:

| Base, alvo 1,25 R e stop 1,5 ATR | Amostras | Lucrativas | Não lucrativas | Ajuste permitido |
|---|---:|---:|---:|---|
| Tendência | 337 | 132 | 205 | Sim |
| Tendência com prazo maior | 297 | 119 | 178 | Sim |
| Retorno à média | 205 | 117 | 88 | Sim |
| Retorno à média com prazo maior | 96 | 60 | 36 | Não |

O modelo ajustado com o prefixo preservado foi idêntico ao modelo obtido repetindo sua simulação. Essa conferência sustenta a reutilização de dados de treino, sem demonstrar vantagem de negociação. O caso de 96 operações continuou recusado; não foi arredondado para 100 nem recebeu requisito menor.

Um ensaio de processamento separado, com oito tarefas e 6.000 candles conhecidos, comparou a sequência de trabalhadores 2/4/4/2 nesta máquina i7-10510U. As medianas foram 13,68 e 9,67 segundos, com o mesmo hash dos resultados financeiros nos quatro ensaios (cerca de 29% menos tempo no lote medido). A rotina desta máquina passa a usar quatro trabalhadores; isso não é promessa de aceleração em qualquer equipamento ou no download de rede.
