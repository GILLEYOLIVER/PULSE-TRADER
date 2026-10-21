# Recuperação da fonte e reserva de avaliação

## Falha observada

A rodada `20261021T051421316409` concluiu o desenvolvimento BTC de cinco minutos, mas falhou no download externo e nos grupos seguintes por indisponibilidade de conexão. Os 11 grupos com falha foram preservados com motivos e arquivos; não geraram nova evidência financeira. As janelas que já estavam reservadas continuam consumidas, inclusive quando nenhum resultado foi produzido. Nenhuma reserva antiga foi apagada.

Consultas posteriores aos endpoints públicos de leitura responderam HTTP200. Isso demonstra recuperação naquele instante, sem garantir disponibilidade contínua.

## Comportamento dos próximos lotes

1. Verificar a disponibilidade da fonte antes de iniciar qualquer grupo.
2. Repetir a mesma consulta de leitura no máximo três vezes para erros de conexão ou HTTP500/502/503/504, com pausas curtas. Dados inválidos, problemas de permissão e HTTP418/429 não são repetidos automaticamente pelo leitor de pesquisa. O prazo `Retry-After` de restrições fica salvo em `provider-backoff.json`, impedindo inclusive o diagnóstico da fonte antes de expirar. Não há troca de host para contornar restrições.
3. Baixar e validar somente o desenvolvimento. Uma falha nessa fase não reserva o teste externo, que ainda não foi solicitado. Essa é uma mudança prospectiva do protocolo.
4. Registrar a escolha e o modelo congelados. Reservar a janela e salvar o estado **antes** da primeira consulta externa. Depois disso, ela permanece consumida mesmo em falhas ou resultados adversos.
5. Se as tentativas de conexão se esgotarem ou a fonte exigir espera, preservar a falha e adiar os grupos que ainda não começaram. Não continuar abrindo janelas em uma sequência de falhas. Lotes adicionais da mesma chamada também são adiados.

O estado `DEFERRED_PROVIDER_UNAVAILABLE` descreve a execução, não um resultado de mercado. A continuidade só poderá iniciar outro lote após verificar novamente a fonte e a cota autorizada. Essa recuperação não altera posições, parâmetros congelados, custos ou registros financeiros.

Os testes verificam indisponibilidade inicial e no meio de um lote, limite de tentativas, separação entre erros transitórios e restrições HTTP, ausência de reserva em falha de treino e manutenção da reserva quando o pedido externo falha depois do congelamento.

Referência: [Binance: limites e códigos HTTP da API pública](https://developers.binance.com/en/docs/products/spot/rest-api). A documentação exige recuar diante de restrições e informa o prazo pelo cabeçalho de resposta. O PULSE usa somente consultas de mercado, sem chamadas de ordens.
