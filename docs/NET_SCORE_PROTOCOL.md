# Experimento de pontuação líquida por risco

## Hipótese

Uma operação vencedora pequena e uma perdedora grande têm rótulos 1 e 0, mas efeitos financeiros diferentes. A candidata BTC anterior que acertou 12 de 20 operações perdeu 364,78 USDT. Esse resultado não basta para atribuir a causa a um fator único; motiva comparar um filtro que também aprende a magnitude líquida das operações passadas.

## Regras para as próximas avaliações

O classificador logístico anterior continua disponível. A nova variante mantém exatamente seus pesos de acerto e acrescenta uma regressão linear L2 do resultado líquido dividido pelo orçamento de risco do treinamento. O professor permanece o simulador PAPER com custos, entradas, stops e alvos reais da simulação.

- Entram as mesmas operações naturais encerradas antes do corte. Continuam exigidas 100 amostras e 20 por classe, limitadas às 3.000 recentes. O valor líquido deve concordar com seu rótulo de acerto.
- A nova saída é uma pontuação em unidades de risco. Não é probabilidade, promessa de caixa ou modelo validado de retorno futuro. `Decision.confidence` permanece indisponível.
- Nenhuma perda é cortada ou removida do alvo. A média e o desvio do resultado líquido são calculados somente no treino; o piso de escala é 10^-6. A regressão usa 120 passos, taxa 0,05 e regularização 0,05 fixos, sem escolher esses valores pelo teste externo.
- A entrada exige a pontuação de acerto já declarada e, adicionalmente, pontuação líquida superior a 10^-6 R. Essa tolerância evita aprovação de zero por ruído numérico. O filtro só pode impedir uma proposta: não muda entrada, stop, alvo, quantidade ou limites de risco.
- As características e o corte temporal são os mesmos para as duas variantes. As operações do primeiro prefixo são compartilhadas e verificadas; o classificador extraído do ajuste conjunto é idêntico ao ajuste anterior, com hash próprio e sem compartilhar listas mutáveis.
- Custos e instrumento de treino continuam no modelo; o orçamento de risco usado para normalizar o alvo também fica registrado. Qualquer adoção na interface exige verificar as premissas do usuário e não é feita por este experimento.

## Tentativas e congelamento

Até duas bases elegíveis recebem as duas variantes (classificação e classificação com pontuação líquida), cada uma nos quatro cortes 0,55/0,65/0,80/0,90. O máximo futuro passa de oito para **16 candidatas aprendidas** por grupo e fica explícito no protocolo e na contagem de tentativas. A grade técnica continua limitada pelo argumento da rodada.

Os mesmos três blocos cronológicos e gates financeiros valem para ambas. Apenas uma candidata é escolhida no desenvolvimento; seu modelo final é ajustado e congelado antes de pedir qualquer candle externo. A referência original continua executada em seu próprio código. Não se escolhe entre 16 resultados externos. A fonte congelada da rodada `20261021T051421316409` não é modificada por este experimento.

Integridade, origem, período de treinamento, dimensões e unidades são validados antes de inferir. Pontuação negativa, insuficiente ou desvio extremo provoca abstenção, sem acerto inventado para ausência de operações. Ganho só poderá ser reconhecido pelos resultados financeiros e pela confirmação posterior em dados inéditos.

## Verificação mecânica

Os testes sintéticos incluem 80% de rótulos vencedores com média líquida negativa: o classificador aceita a pontuação de acerto, mas a nova variante bloqueia a proposta. Também verificam caixa positivo, média zero com ruído, conservação de uma perda extrema no alvo, rótulos inconsistentes, corrupção de modelo, equivalência do classificador anterior e congelamento da variante correta. Esses exemplos não são evidência de acerto em mercado.

## Ensaio em desenvolvimento conhecido

A base congelada anteriormente foi reaplicada ao desenvolvimento BTC de cinco minutos de 27/01 a 26/02/2018, já conhecido. Cada par usou os mesmos três blocos e pontuações de acerto. Não é avaliação externa nova:

| Corte | Classificação: vitórias/operações | Líquido USDT | Com filtro líquido: vitórias/operações | Líquido USDT |
|---|---:|---:|---:|---:|
| 0,55 | 107/151 | -1.203,65 | 44/58 | -73,12 |
| 0,65 | 54/66 | +423,90 | 37/46 | +242,35 |
| 0,80 | 1/1 | +21,80 | 1/1 | +21,80 |
| 0,90 | 0/0 | 0,00 | 0/0 | 0,00 |

A variante líquida não ficou elegível em nenhum corte. Em 0,65 houve perdas em dois blocos, apesar do total positivo; o classificador anterior manteve seus resultados exatamente. Uma vitória ou ausência de operações não fornece amostra. Portanto, esse conjunto não sustenta substituir a referência pelo filtro novo. Os resultados e modelos ficam preservados para comparação, sem contarem para a meta.
