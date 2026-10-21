# Ciclo de pesquisa do PULSE

## Missão e medida

Buscar mais de 90% de operações encerradas com resultado líquido positivo, após os custos declarados. A porcentagem refere-se a operações, não a candles previstos ou testes de software. A meta pode não ser alcançável; não será declarada sem resultados. Não há execução real.

Cada ativo e prazo tem sua própria versão de referência de pesquisa. O ciclo preserva configurações, código, dados e relatórios. Uma melhoria em Bitcoin não é transferida automaticamente para Ethereum. O risco, o capital, os custos e as unidades dos instrumentos são iguais entre as versões comparadas. Limites de política, como o alvo/risco mínimo e as estratégias permitidas, podem diferir e ficam explícitos no protocolo.

O universo inicial desta rotina é BTCUSDT, ETHUSDT, BNBUSDT e SOLUSDT em candles de 5 minutos, uma hora e um dia. A meta do conjunto só é declarada quando as referências dos grupos acompanhados cumprirem a confirmação; um ativo isolado não encerra a missão.

## Protocolo antes dos resultados

1. Reservar uma janela externa inédita e registrar o protocolo. Históricos antes usados como avaliação continuam identificados. Falha de download não torna a janela nova novamente.
2. Usar somente histórico anterior à janela externa, com três blocos cronológicos de validação e aquecimento anterior sem ordens. O motor recebe um candle encerrado por vez, com execução posterior.
3. Comparar a referência e candidatas determinísticas de tendência, rompimento, retomada e médias móveis. Os filtros candidatos medem separação/inclinação das médias, eficiência direcional, volume e distância até a média. Stops permanecem sujeitos ao orçamento central de risco.
4. Exigir amostra, lucro líquido e consistência nos blocos de desenvolvimento. Priorizar limite inferior descritivo do acerto entre as candidatas elegíveis, além de expectativa, perdas e custos. Ausência de candidata elegível preserva a referência e registra insuficiência.
5. Congelar uma candidata antes de abrir o período externo. Comparar somente essa candidata com a referência, incluindo custos dobrados. Não escolher a maior porcentagem entre vários testes externos.
6. Promover para referência das pesquisas somente uma candidata que cumpra os critérios declarados e melhore a referência na mesma janela. Guardar a referência anterior para recuperação. Isso não muda posições/configurações da sessão da interface.
7. Gerar relatório completo, preservar rejeitadas e continuar em outra janela. Sem dados inéditos suficientes, registrar espera e procurar outro ativo/prazo permitido.

## Hipóteses da segunda iteração

As primeiras matrizes mostraram perdas líquidas em vários blocos intradiários e amostras diárias pequenas. A próxima iteração inclui candles de uma hora para estudar o peso dos custos em movimentos maiores, quatro anos de desenvolvimento diário para BNB/SOL e um candidato de retorno à média: recuo com RSI2 de Wilder extremo dentro de tendência SMA200 confirmada, alvo na média5 limitado pelo múltiplo de risco e stop estrutural/ATR de no máximo 3 ATR.

A grade predefinida inclui alvos de 0,5/1/1,25/2/3 R e stops de 1,5/2,5 ATR. Apenas na pesquisa, o alvo/risco mínimo líquido é 0,25, igual para referência e candidatas. Isso permite estudar alvos menores sem aumentar o orçamento de perda por operação de 0,25% do capital. Alvos menores podem aumentar o acerto e reduzir o ganho por operação; lucro líquido, perdas e custos dobrados continuam obrigatórios para promoção. Nenhuma taxa foi reduzida para melhorar resultados: a premissa permanece 0,1% por lado, mais spread/slippage, e o stress dobra custos.

Ausências reais de candles são registradas no manifesto e preservadas sem preenchimento. Candles que a origem encerrou antes do fim nominal também são identificados; só se tornam disponíveis ao motor depois do fim nominal, nunca antecipadamente. O motor cancela entradas pendentes diante de lacunas e mantém a proteção de posições. Mais de 5% de candles ausentes invalida o conjunto. A consulta normal da interface continua exigindo histórico contíguo por padrão. Janelas interrompidas ou com falha ficam registradas e não são reapresentadas como inéditas.

## Critério de meta

A iteração de aprendizado com operações encerradas segue [o protocolo do filtro de entradas](TRADE_MODEL_PROTOCOL.md). São no máximo oito candidatas adicionais por grupo, com pontuação não calibrada, modelos ajustados somente no passado de cada bloco e os mesmos critérios financeiros. O desenvolvimento usa 30 dias em cinco minutos e 365 dias em uma hora. O contexto externo inicialmente exigia 250 candles; os próximos lotes da [iteração multitemporal](MULTI_TIMEFRAME_PROTOCOL.md) exigem 1.024 e incluem variantes com confirmação por prazo maior, sem alterar rodadas abertas.

A [iteração de histórico ampliado](LONG_HISTORY_PROTOCOL.md) passa, somente nos próximos lotes, a 90 dias de desenvolvimento em cinco minutos, 540 dias em uma hora e quatro anos nos diários. Os tamanhos anteriores continuam registrados em seus protocolos originais. A amostra do professor é verificada antes da escolha de até duas bases para modelos.

Uma porcentagem isolada acima de 90% não encerra a missão. A mesma versão congelada precisa de pelo menos três janelas externas distintas, somando pelo menos 100 operações, mais de 90% de operações lucrativas em cada janela, lucro líquido em cada janela e resultado positivo com custos dobrados. O relatório mostra intervalo de Wilson descritivo e número de tentativas. Não é garantia de probabilidade futura, nem um teste estatístico corrigido por todas as escolhas de pesquisa.

Os relatórios mantêm taxas de abstenção, bloqueios e encerramentos forçados. Operações negativas e dias adversos não podem ser removidos. Mudar o alvo/stop ou o código cria uma nova versão e reinicia a confirmação daquela versão. Dados sintéticos servem a testes mecânicos e nunca qualificam a meta.

## Persistência e continuidade

### Comparação com a implementação original

A partir da iteração de referência arquivada, a referência externa é executada em outro processo Python, importando apenas sua cópia original de código, parâmetros, custos e limites. Os mesmos candles e contexto são entregues à candidata e à referência. Não há acesso à rede nem alteração do registro pelo processo de controle. Falha de integridade ou incompatibilidade interrompe aquela avaliação; não há substituição silenciosa pela implementação atual.

As primeiras rodadas preservaram o código, mas reaplicaram parâmetros antigos ao motor novo. Esses resultados continuam identificados por suas versões próprias e não confirmam a implementação antiga. As mudanças automáticas com motivo `REFERENCE_PARAMETERS_REEVALUATED_ON_NEW_CODE` são restauradas para a última referência inicial ou promovida por validação e teste externo. O histórico completo permanece no registro, incluindo essa restauração. Uma tradução dos parâmetros antigos pode participar do desenvolvimento como semente do código atual, mas não representa a execução da referência antiga.

O controle preserva inclusive o aquecimento original: não corrige o algoritmo antigo durante a comparação. Importações são isoladas do projeto atual e os fontes são verificados por hash. O relatório inclui identificação do código original, da pasta materializada, do transportador de dados, diferenças explícitas de política, decisões e métricas normais e com custos dobrados. Um inicializador vazio de pacote é a única estrutura adicional permitida para arquivos antigos que não o incluíam.

### Janelas ampliadas antes de novas avaliações

Após a rodada `20261021T035539524994`, somente os próximos testes externos passam a usar 28 dias em cinco minutos e 90 dias em uma hora, mantendo 90 dias nos diários. O desenvolvimento continua com 30/365 dias e quatro anos nos diários BNB/SOL. A escolha é anterior aos novos resultados e busca amostras maiores; nenhum período já aberto é ampliado retroativamente. Os limites de operações, lucro, custos dobrados e perda máxima permanecem. Esse tamanho, incluindo 250 candles anteriores, cabe no limite de 10.000 candles por consulta.

`runtime/aprendizado/ciclos/` contém versões imutáveis por hash, cópias do código e estado das referências de pesquisa. `reports/research-cycles/` contém protocolo, matrizes, dados de origem, decisões, resultados e relatório de cada rodada. A rotação usa também o registro anterior `historicos_utilizados.json`.

As rodadas são executadas a partir de uma cópia congelada do código em `workspaces/`, de modo que alterações posteriores no projeto não mudem seus processos de cálculo. Cada grupo concluído gera também um arquivo completo em `runtime/aprendizado/ciclos/runs/`, com dados, decisões e relatórios, para inclusão no backup normal da pasta de dados. Uma referência só muda depois de esse arquivo ter sido preservado e verificado. Os dados em cripto não qualificam WIN/WDO nem a conexão real com corretora.

Cada chamada executa um lote limitado; a continuidade pode invocar novos lotes sem executar processos infinitos. Apenas uma instância altera o registro de ciclos por vez. Uma interrupção preserva os arquivos já gravados e não confirma uma rodada incompleta.

Comandos na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m scripts.research_cycle --plan-only
.\.venv\Scripts\python.exe -u -m scripts.research_cycle --cycles 1 --workers 2 --candidates 36
```

O registro `latest.json` aponta o relatório mais recente; referências anteriores e seus códigos são imutáveis e verificadas por hash. Os blocos de desenvolvimento usam avaliação de métricas sem guardar cada decisão; os testes externos mantêm todas as decisões. Os testes de equivalência verificam os mesmos custos, operações, perdas e bloqueios nos dois caminhos.

## Regra de consumo definida pelo usuário

Antes de cada lote e durante etapas prolongadas, consultar a ferramenta oficial de limites do Codex e localizar a janela semanal de 10.080 minutos. Interromper a tarefa quando restarem **40% ou menos** da cota (uso igual ou superior a 60%). Preservar os arquivos, interromper os processos de pesquisa identificados desta tarefa e pausar a continuidade e o objetivo. A renovação da cota não autoriza retomada automática. Se o saldo estiver indisponível, aguardar a consulta antes de iniciar outro lote. O programa de simulação não recebe credenciais da conta Codex; essa conferência pertence à rotina do assistente.

Referências consultadas: [Freqtrade: detecção de acesso ao futuro](https://www.freqtrade.io/en/stable/lookahead-analysis/) e [QuantConnect: otimização em janelas móveis](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization). O protocolo e os filtros são implementações próprias.
