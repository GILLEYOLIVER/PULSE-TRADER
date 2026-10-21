# Integrações oficiais — pesquisa em 20/10/2026

## Situação da versão entregue

PAPER e CSV funcionam sem serviços pagos. Não existe conexão ativa com Rico ou Profit.
`BrokerPort` define operações de fronteira; `RicoProfitAdapter` é deliberadamente bloqueado,
não uma implementação de SDK. Seus métodos são testados para impedir execução real.

## O que foi confirmado

A documentação oficial da Nelogica descreve ProfitDLL para Market Data e um modo adicional
com roteamento, cancelamento e consultas. Requer licença e habilitação da conta na corretora.
A presença desse produto não confirma o direito de uma conta Rico específica usá-lo.
Não foi encontrada confirmação suficiente de uma API pública direta da Rico para este projeto.
A Nelogica informa que o pacote e manual da ProfitDLL são obtidos após contratação pela área logada.
Sua documentação também diz que contas Rico não podem ser incluídas em licenças de teste do Profit;
isso não demonstra incompatibilidade com uma licença comercial ProfitDLL, que continua sem confirmação.

Fontes primárias:

- [Introdução ao Produto DLL Real Time](https://ajuda.nelogica.com.br/hc/pt-br/articles/11166353435035-Introdu%C3%A7%C3%A3o-ao-Produto-DLL-Real-Time)
- [Ecossistema ProfitDLL e primeiros passos](https://ajuda.nelogica.com.br/hc/pt-br/articles/22396517026203-Ecossistema-ProfitDLL-e-primeiros-passos)
- [Como obter acesso à ProfitDLL](https://ajuda.nelogica.com.br/hc/pt-br/articles/51583791325211-Como-obter-acesso-%C3%A0-ProfitDLL)
- [Conta Rico em licença de teste do Profit](https://ajuda.nelogica.com.br/hc/pt-br/articles/360044286392-Como-integrar-minha-corretora-na-licen%C3%A7a-de-teste-do-Profit)
- [Módulo de Automação de Estratégias](https://ajuda.nelogica.com.br/hc/pt-br/articles/18501196212251-Conhe%C3%A7a-o-m%C3%B3dulo-de-Automa%C3%A7%C3%A3o-de-Estrat%C3%A9gias)

A automação nativa do Profit utiliza estratégias NTSL. Não executa Python diretamente.
EMA, ATR e filtros simples podem ser candidatos a tradução, mas sem equivalência validada nesta entrega.
ML Python, ledger SQLite, custos e regras de portfólio exigem outro desenho; não há tradução automática.

## Dependências de uma futura integração

Confirmar com Rico/Nelogica a conta elegível, broker exato, licença, direitos de dados, contratos,
ambiente de simulação, distribuição do SDK e custos. Obter os headers oficiais antes de vincular funções.
Separar callbacks de processamento; exigir os estados de login, dados, ativação e corretora prontos.
Reconciliar IDs de ordens, confirmações, posições e saldo após quedas antes de liberar novas entradas.
Manter retenção das referências de callbacks e validar arquitetura do processo/DLL.

Taxas de assinatura, dados e roteamento não foram cotadas nem contratadas; dependem da oferta e permissões.
Não assumir que uma assinatura comum de Profit inclui ProfitDLL. Nenhuma senha de produção é necessária agora.
Nenhuma alteração de configuração nesta versão habilita REAL. Uma futura versão dependerá de autorização
explícita, implementação oficial, testes de sandbox e homologação operacional.

## Especificações dos instrumentos

- [WIN — B3](https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/futuro-mini-de-ibovespa.htm)
- [IND — B3](https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/futuro-de-ibovespa.htm)
- [WDO — B3](https://b3.com.br/pt_br/produtos-e-servicos/negociacao/moedas/futuro-mini-de-taxa-de-cambio-de-reais-por-dolar-comercial.htm)
- [DOL — B3](https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/moedas/futuro-de-taxa-de-cambio-de-reais-por-dolar-comercial.htm)

Somente fontes fornecidas/licenciadas pelo usuário são importadas. A aplicação não redistribui cotações.
