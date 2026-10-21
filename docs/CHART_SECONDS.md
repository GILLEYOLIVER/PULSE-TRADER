# Zoom e gráficos em segundos

O gráfico oferece **1, 5, 10, 15 e 30 segundos** quando o histórico de origem permite.
Um arquivo de um minuto continua oferecendo apenas um minuto ou períodos maiores.
Não se inventam candles menores por interpolação. Os horários do eixo incluem segundos.

## Usar

- **Simulação 1 s** carrega um exemplo identificado como SYNTHETIC. Depois, use Iniciar
  replay ou Próximo candle e escolha o período em Cada candle. Não são cotações reais.
- Um CSV com `seconds=1` permite os cinco períodos. O conversor do Profit também aceita
  segundos, desde que esse seja realmente o período do arquivo autorizado.
- Em **Sugestões > Fontes e atualização**, escolha Binance e BTCUSDT, ETHUSDT, BNBUSDT
  ou SOLUSDT. Os períodos em segundos consultam explicitamente a **última hora**.
  O sistema usa candles nativos de um segundo e agrupa apenas blocos completos em UTC.
  Valores continuam em USDT; as regras de moeda e risco precisam ser respeitadas no replay.
  A consulta é somente de leitura e a atualização opcional continua a cada 60 segundos.

Mudar Cada candle ajusta a visualização. O motor continua recebendo os candles do replay
carregado; essa seleção não muda uma estratégia, stop ou posição aberta. A nova simulação
exige ausência de posições/ordens pendentes e preserva as operações anteriores.
Sua resolução e data inicial ficam salvas para reconstruir o mesmo exemplo ao reabrir.

## Desenho

Eventos próximos de zoom e navegação compartilham um redesenho agendado. Durante o
movimento, candles e médias usam o Canvas; depois de parar, a imagem com suavização em
resolução dobrada é refeita. O envio dessa imagem ao Tk usa RGB opaco com a grade sob os
candles, evitando o custo de composição alfa de toda a área. Os textos continuam vetoriais.
Sem Pillow, continua disponível o renderizador anterior de linhas suavizadas.

O cache contém somente candles completos e séries EMA9/21 da visualização. O conteúdo dos
candles faz parte da chave, com limite de quatro entradas; não guarda aprovações de risco.
O zoom não recebe candles futuros, não avança o replay e não envia ordens.

## Verificação

O ensaio local preserva a implementação anterior em `reports/chart-zoom-20261021/`.
Compara a mesma série sintética, tamanho de Canvas, 24 eventos, enquadramento final,
hash das médias/candles e estado do ledger. Mede tanto o desenho detalhado quanto a
sequência completa de zoom. Medições parciais/erros do observador ficam preservados.
O resultado descreve esta máquina, com pesquisa em segundo plano; não é uma promessa
de desempenho universal ou ganho de acerto financeiro.

Nas duas medições de cada implementação, o redesenho detalhado passou de mediana
0,983 s para 0,082 s (aproximadamente 12 vezes mais rápido). A sequência de 24 eventos
passou de 22,971 s para 0,359 s, incluindo o desenho final detalhado. O enquadramento,
os candles/EMAs e o ledger foram conferidos em todas as execuções aceitas.

Testes verificam candles de um segundo encerrados, agrupamento sem preencher lacunas,
atividade preservada, exclusão de blocos incompletos, resolução compatível com a fonte,
restauração do exemplo e ausência de ordens por interações do gráfico.

Fonte primária: [Binance: candles e intervalos suportados](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market#klinecandlestick-data).
