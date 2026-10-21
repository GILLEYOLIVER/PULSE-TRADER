# Upgrade 2.1 — os seis passos

Execução financeira exclusivamente PAPER. Pasta do projeto: `C:\Users\A1\Documents\ChatGPT\PR-TR`.

## 1. Integração da atualização

O PR #2 foi revisado, testado e integrado por solicitação explícita do usuário.
O commit de integração é `f09ee7c3be4e1fbfbfac7fdba59f92500b9871b3`.
Esta continuação acrescenta os passos abaixo no [PR #3](https://github.com/GILLEYOLIVER/PULSE-TRADER/pull/3),
com testes do código, da interface e do executável antes da integração solicitada.

## 2. Dados públicos e Profit

**Fontes e atualização** oferece consulta somente de leitura e atualização opcional a cada 60 segundos.
A brapi permite experimentar PETR4, VALE3, ITUB4 e MGLU3 sem token; outras consultas dependem do plano
e da variável de ambiente `BRAPI_TOKEN`. A aplicação não grava o token nem recebe senhas de corretora.
Mercado Bitcoin fornece candles públicos de BTC/ETH spot em BRL. A disponibilidade e o atraso pertencem
ao provedor; a tela exibe origem e horário. Atualizar o catálogo não avança o replay nem envia ordens.

Fontes: [brapi](https://brapi.dev/docs/acoes/historico),
[autenticação brapi](https://brapi.dev/docs/authentication),
[Mercado Bitcoin](https://api.mercadobitcoin.net/api/v4/docs).

O conversor do Profit aceita cabeçalhos em português, separador local, decimal com vírgula,
ordem cronológica invertida, timestamp de abertura/encerramento e Volume Quantidade.
Volume Financeiro não é usado como quantidade. Contratos não são convertidos silenciosamente
para outro ticker, e OHLC não é misturado com um fechamento ajustado isoladamente.
Arquivos sem identificação do ativo exigem que o usuário informe o código.
WIN/WDO ainda exigem um histórico autorizado do Profit ou serviço habilitado; não foi contratado um feed.

## 3. Validação em histórico real

O estudo separa 60% de treino, 20% para seleção e 20% de teste final. A seleção de estratégia usa
somente a validação. O holdout é avaliado depois, com custos e um cenário adicional de custos maiores.
O modelo logístico é treinado só no treino, calibrado na validação e medido no teste, com Brier e ECE.
Uma estimativa só é mostrada como calibrada quando passa pelos critérios registrados no modelo;
dados sintéticos nunca aprovam esse critério. Modelos fora da distribuição ou posteriores ao replay
não fornecem probabilidades naquele cenário. Não há adoção automática.

Estudo público executado em 20/10/2026, sem alterar capital ou exposição do banco do usuário:

| Série | Candles encerrados | Operações no teste | Líquido PAPER após custos | Evidência suficiente |
|---|---:|---:|---:|---|
| PETR4, 1 minuto | 1.206 | 12 | -R$ 458,39 | Não |
| PETR4, diário | 496 | 3 | R$ 1.740,14 | Não |
| VALE3, 1 minuto | 1.202 | 12 | -R$ 584,79 | Não |
| VALE3, diário | 496 | 3 | R$ 177,00 | Não |

Esses resultados são estudos, não uma carteira nem previsão de rentabilidade. Premissas explícitas:
capital PAPER R$100.000, risco 0,5% por operação, reserva de R$100 por ação, lote 100, taxa R$0,01
por unidade/lado, spread e slippage de um tick. Não são tarifas ou margens oficiais. Os resultados
não incluem proventos, impostos, aluguel, fila ou todos os eventos de mercado. Três operações diárias
não justificam conclusão de vantagem. Nenhum dos quatro modelos foi aprovado para probabilidade calibrada.

Dados e relatórios completos ficam localmente em `reports/public-validation/`, com hashes e parâmetros.
Para repetir o estudo: `python -m scripts.validate_public --install-data runtime`.
O comando instala apenas catálogo/contexto/modelos de análise; não altera `paper.sqlite`.

## 4. Do plano à ordem PAPER

**Guardar plano** continua apenas arquivando a proposta. **Levar ao replay** prepara o histórico em
lotes sem entradas automáticas e mantém a janela disponível. **Armar entrada PAPER** confere a
origem, o hash dos últimos candles, a data exata, configurações e especificação do instrumento.
Os limites, margem e exposição são avaliados antes da aprovação e novamente ao preencher.

Sinal já formado gera ordem pendente para um candle posterior. Plano condicional aguarda um novo
candle encerrado que confirme preço e volume, respeitando filtro multitemporal quando habilitado.
O monitoramento condicional exige **Simulação automática** ligada. A validade é de três candles
da série. Configuração alterada, prazo vencido, risco bloqueado ou dados incompatíveis impedem a entrada.
Plano, ordem e auditoria são gravados em transação SQLite; repetição não duplica ordens.
O estado do plano acompanha execução, cancelamento e encerramento da ordem.

## 5. Contexto de empresas

A consulta de ações reúne métricas financeiras de 12 meses, proventos e comunicados da CVM:
lucro/margem, caixa livre, dívida líquida/EBITDA, datas ex e fatos relevantes.
Esse contexto gera alertas e necessidade de revisão antes de armar uma proposta de dias/semanas.
Não atribuímos sentimento ou probabilidade de valorização a um título de notícia.
Comunicados ficam associados à companhia por CNPJ obtido do perfil do provedor.

Snapshots atuais são excluídos de um replay anterior à consulta; datas sem hora são admitidas
depois do dia completo da publicação. O histórico de preço não recebe retrospectivamente balanços
atuais. O P&L do simulador ainda é de preço, sem crédito automático de dividendos ou custo de aluguel.
Fontes: [financeiro brapi](https://brapi.dev/docs/acoes/dados-financeiros),
[proventos](https://brapi.dev/docs/acoes/dividendos), [CVM IPE](https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe).

## 6. Interface, dados locais e executável

Todos os parâmetros de risco, execução, estratégia, calendário e especificações podem ser editados
em formulários. JSON permanece disponível para compatibilidade. Backtests, treino, downloads e
validação rodam em segundo plano; callbacks e SQLite da sessão continuam na thread principal.

O banco é um arquivo local: não exige instalar SQLite nem um servidor. No executável portátil,
`runtime` fica ao lado do programa, salvo escolha explícita de outra pasta.
`iniciar-portatil.cmd` usa o executável compilado e o `runtime` do projeto, preservando os dados já existentes.

Backups usam a API online do SQLite e incluem os arquivos auxiliares locais. A restauração verifica
hashes, caminhos e integridade dos bancos, e só escreve em pasta vazia. A UI permite abrir a pasta
restaurada sem comandos. Restaurar um backup antigo também restaura o relógio/limites da simulação.

`scripts/build.ps1` cria uma versão em `dist/<commit>/PulseTrader/`, roda o teste interno do executável
e produz um ZIP portátil. O empacotamento inclui Python, Tk, SQLite, interface e timezone.
Versões com `runtime` existente não são apagadas ao reconstruir. Não há instalação de serviços,
aceite de licenças pagas, corretora real, assinatura de código ou homologação em outro computador.

### Pacote verificado nesta entrega

- Código empacotado: `b2d18cc01509da47fb84b7527fd57a9e5e7bf0fa`.
- Executável: `dist/b2d18cc/PulseTrader/PulseTrader.exe`.
- ZIP portátil: `dist/b2d18cc/PulseTrader-Windows-Portable.zip` (22.374.695 bytes).
- Teste do executável compilado: `reports/portable-smoke.json`, `ok=true`, `frozen=true`, modo PAPER.
- Verificações: replay de 80 candles, sugestões, formulários, carregar replay, armar/cancelar plano,
  backup/restauração, tarefas em segundo plano e SQLite incluído.
- Código: 78 testes aprovados, compilação de módulos e teste de interface aprovados.

Abra `iniciar-portatil.cmd` para usar o pacote com os dados atuais em `runtime` do projeto.
Para levar a outro computador, extraia o ZIP e mantenha a pasta inteira do programa;
o executável criará seu próprio `runtime` ao lado dele. O ZIP não contém os dados pessoais
do projeto. Use o recurso de backup/restauração para transferi-los quando necessário.
