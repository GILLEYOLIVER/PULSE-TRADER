# Hipótese prospectiva: resultado por risco inicial executado

## Motivo e definição

O desenvolvimento BTC de cinco minutos já conhecido (30/01 a 30/04/2018) teve uma variante
logística com 104 vitórias em 146 operações (71,23%), mas líquido de -296,11 USDT.
Não ficou elegível: dois dos três blocos perderam. Mais acertos não demonstraram vantagem financeira.

O filtro líquido anterior ajusta `net / orçamento máximo por operação`. Margem, exposição, lotes,
liquidez e bloqueios podem fazer a posição usar somente parte desse orçamento. A nova hipótese
ajusta `net / caixa de perda no stop inicial da quantidade realmente executada`, incluindo custos.
O resultado em múltiplos do risco inicial é uma medida descrita pelo
[Van Tharp Institute](https://vantharpinstitute.com/tharp-think-trading-concepts/).
Acrescentar taxas e execução adversa à definição é uma decisão desta implementação.
Isso não implica que a normalização melhorará as próximas operações; a vantagem precisa ser testada.

## Alvo, causalidade e compatibilidade

- `initial_stop_cash` usa entrada real, stop inicial, quantidade preenchida e taxas reais de entrada,
  mais a saída adversa e taxa no stop. Não usa o stop já ajustado por trailing ou break-even.
- O valor é anexado apenas ao rótulo de uma operação natural já encerrada. Características continuam
  registradas no sinal, antes do fill. Não se usa resultado futuro para decidir a entrada.
- Toda perda, inclusive gap maior que 1R, fica no alvo sem corte. Encerramentos forçados permanecem
  nas métricas e continuam excluídos do ajuste independentemente do sinal financeiro.
- Amostra, classes, normalização temporal, drift, L2, 120 passos, taxa 0,05, 18 características e corte
  de caixa positivo maior que 10^-6 R permanecem iguais. A saída continua sem calibração probabilística.
- A variante recebe identificador próprio. Ela deriva do mesmo ajuste conjunto, verifica o hash exato
  dos rótulos e não altera os pesos do classificador. Unidades ausentes, inválidas ou incompatíveis
  são recusadas. Modelos antigos mantêm sua interpretação e implementação arquivada.
- Nenhum risco, preço de entrada, stop, alvo ou limite é ampliado pelo filtro; ele apenas pode bloquear.

## Tentativas futuras e confirmação

Somente nas próximas fontes congeladas, até duas bases elegíveis recebem três modelos: classificação,
caixa/orçamento e caixa/risco inicial. Cada um usa os quatro cortes 0,55/0,65/0,80/0,90.
O máximo passa de 16 para **24 variantes aprendidas** por grupo, contado antes dos resultados.
Os mesmos três blocos e gates financeiros/amostrais valem para todos. Só uma candidata é congelada
antes do primeiro pedido externo; não se escolhe entre vários resultados externos.

A rodada aberta `20261021T055244566903` continua com sua fonte original e máximo de 16 variantes.
Seus dados, modelos, critérios e resultados não são alterados. Uma regressão conhecida desta hipótese
serve somente para diagnóstico, sem promoção e sem contar para a meta superior a 90%.

Interface, referências preservadas e ordens reais não são alteradas pelo experimento.
