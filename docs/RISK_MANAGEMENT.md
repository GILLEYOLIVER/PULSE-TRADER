# Gestão de risco

Limites são independentes das estratégias e também se aplicam a ordens manuais e backtest.
Meta diária é condição de parada; não é previsão de ganho.

Risco unitário = distância da entrada ao stop × valor por ponto + taxas de entrada/saída + reserva de execução.
Quantidade é arredondada para baixo ao lote permitido e limitada por contratos, margem simulada e exposição.
Se o orçamento não comportar um lote, a ordem é rejeitada. Scores e perdas anteriores nunca aumentam o risco.
A entrada é reavaliada ao preço de fill; gaps podem reduzir a quantidade ou rejeitar a ordem.

| Ativo | R$/ponto ou unidade | Tick | Lote |
|---|---:|---:|---:|
| WIN | 0,20 | 5 | 1 |
| IND | 1,00 | 5 | 5 |
| WDO | 10,00 | 0,50 | 1 |
| DOL | 50,00 | 0,50 | 5 |
| PETR4 / VALE3 | 1,00 | 0,01 | 100 |
| BTC / ETH spot BRL | 1,00 | 0,01 | 1 |

Crypto usa unidade inteira por simplificação; não representa lotes de exchange ou futuros.
Margem padrão R$1.000 por unidade e taxa R$0,50 por lado são premissas didáticas, não valores da Rico/B3.

Os limites de perda usam P&L realizado + marcação aberta e reservam risco até os stops para novas entradas.
Ordens pendentes reservam orçamento; não contam como fills antes de executar.
Limites diário/semanal/mensal usam datas de São Paulo e incluem taxas. Bloqueios são persistentes por período.
O fallback UTC-3 não reconstrói mudanças históricas de horário de verão; instale tzdata para históricos antigos.

Pausar impede avanço do replay; emergência bloqueia novas entradas e cancela pendências.
Proteções de posições são processadas nos próximos candles; fechar a aplicação pausa tudo.
Gap, falta de liquidez ou OHLC incompleto podem causar perda maior que a configurada. O simulador não oferece
proteções hospedadas na corretora. Não é adequado a operação real.

Expiração de Instrument pode ser configurada no domínio. Séries contínuas não têm rolagem implícita.
SessionCalendar só declara sessão B3 aberta quando fornecido como verificado; o replay não aplica feriados
oficiais automaticamente. Horários start_hour/end_hour restringem a simulação conforme a configuração.

Referências técnicas consultadas em 20/10/2026: páginas oficiais B3 de Futuro Mini de Ibovespa,
Futuro de Ibovespa, Futuro Míni de Taxa de Câmbio e Futuro de Taxa de Câmbio (links em INTEGRATIONS).
