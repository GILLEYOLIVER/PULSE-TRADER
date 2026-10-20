# Sugestões por ativo

A aba **Sugestões** reúne cenários técnicos de vários ativos e mantém dois perfis:

- **No dia:** candles com duração inferior a um dia, como 1, 5, 15 ou 60 minutos.
- **Dias e semanas:** candles diários, com `seconds=86400`. O perfil indica um uso analítico;
  não determina em quantos dias o preço chegará a um alvo.

O indicador combina EMA9/EMA21, posição do preço e impulso. Uma separação inferior a 0,15 ATR
ou sinais discordantes deixa o cenário sem direção confirmada. A tabela usa seta, texto e cor,
sem depender somente da cor. Ao selecionar um ativo, o resumo explica os indicadores,
o volume relativo e a volatilidade que fundamentam o cenário.

Os modelos de regras existentes são avaliados na ordem fixa rompimento, tendência e retomada,
usando `reward_r`, `stop_atr` e o filtro multitemporal configurados na aplicação.
Essa prioridade é uma regra de organização, não uma seleção de desempenho futuro.
Se houver sinal técnico, os preços são referências para o candle seguinte, sujeitos ao risco.
Se houver direção mas nenhum sinal, a tela mostra um gatilho condicional além do suporte/resistência;
o fechamento e o volume ainda precisam confirmar esse gatilho. Um cenário lateral, histórico curto,
volatilidade incompatível ou ativo sem especificação pode ficar sem entrada, stop e alvo.
Preços de proposta respeitam o tick configurado e não são cotações em tempo real.

## Dados e referências

**Adicionar CSVs** aceita vários arquivos de uma vez. As colunas são as mesmas do replay:
`symbol,ts,open,high,low,close,volume,source,seconds`. Use volume em quantidade,
timestamp da abertura com fuso e origem verdadeira. Para o mesmo ativo em períodos diferentes,
importe arquivos separados. O catálogo mantém séries distintas por ativo, período e origem.
Arquivos sobrepostos não podem alterar candles já salvos ou introduzir intervalos sobrepostos.
Uma importação inválida não substitui o catálogo existente.

Cada candle só entra na análise após `ts + seconds`. Nos diários isso exige uma convenção coerente:
por exemplo, uma barra com abertura às 00:00 de São Paulo é considerada encerrada às 00:00
do dia seguinte. A análise pode ficar atrasada em relação ao fechamento do pregão; ela não
adivinha horários de fechamento, feriados ou ajustes corporativos. Normalize esses dados com a fonte.
Não agregamos minutos em um dia de negociação automaticamente.

**Usar replay atual** usa exclusivamente os candles já processados pelo gráfico e acompanha
seu avanço. **Exemplo simulado** mostra séries sintéticas identificadas como `SYNTHETIC`.
**Dados salvos** reabre o catálogo SQLite local (`suggestions.sqlite`) após reiniciar o aplicativo.
**Exportar sugestões** salva o perfil visível, os motivos, preços, datas, origem e hash dos dados.

O botão **Onde obter dados** abre instruções para:

- Exportar históricos do Profit conforme a licença disponível:
  [guia oficial Nelogica](https://ajuda.nelogica.com.br/hc/pt-br/articles/360044287672-Como-exportar-dados-hist%C3%B3ricos-de-ativos-para-o-Excel).
  O arquivo bruto precisa ser convertido para o CSV padrão do PULSE.
- Consultar dados financeiros de empresas na
  [CVM](https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr). Esses dados ainda não entram no cálculo desta aba.

## Planos e execução

**Guardar plano PAPER** grava no ledger uma proposta com análise, fonte/hash, preços,
configurações e orçamento por operação. A gravação é transacional e idempotente;
repetir a mesma proposta não cria cópias nem ordens. `risk_approved=false` e `quantity=null`
indicam que o plano ainda não passou pelo dimensionamento de uma entrada.
O orçamento exibido é capital configurado × fração de risco; não é promessa de perda máxima.

A aba não envia ordens. Entradas manuais/automáticas continuam no motor PAPER, que valida
o risco em cada envio e preenchimento. Uma venda proposta não estabelece disponibilidade de aluguel
ou permissão para venda descoberta. O perfil de dias/semanas não inclui balanços, notícias, dividendos,
tributação, ajuste diário de futuros ou proteção hospedada na corretora.

Esta entrega usa regras técnicas, sem probabilidade calibrada ou previsão comprovada de valorização.
Um setup marcado como sinal significa apenas que suas regras foram atendidas no último candle encerrado.
Os testes verificam a mecânica; não validam rentabilidade.
