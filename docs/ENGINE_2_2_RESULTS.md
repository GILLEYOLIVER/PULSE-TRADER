# PULSE 2.2 — motor, aprendizado e avaliação

Execução exclusivamente PAPER. O motor principal usa regras determinísticas e não depende de IA generativa. Modelos estatísticos são opcionais e não têm permissão para enviar ordens.

## Cálculos e processamento

- Replay de 1.200 candles: 16.42 s com o caminho durável versus 0.70 s no estado descartável de pesquisa, cerca de 23.6 vezes mais rápido nesta máquina.
- Duas execuções finais do caminho rápido: 0,699 s e 0,697 s. Indicadores, ordens e métricas do benchmark original permaneceram idênticos. A sessão PAPER mantém SQLite e transações duráveis.
- Treino de candidatos em dois processos de CPU. Não houve instalação de uma GPU nem aumento de hardware.
- Taxas fixas e proporcionais ao financeiro, custos na entrada/saída, custo de liquidação e reserva do stop; relação alvo/risco após custos opcional.
- Unidades menores de cripto com volume por unidade explícito; spot configurado somente para compras; moedas de conta, ativo e provedor verificadas.
- Break-even considera taxas proporcionais e slippage e aguarda preço suficiente para um stop protetivo válido.

## Métodos de leitura e proteção

Além de tendência, rompimento e retomada, há um candidato por regime/volume/fluxo e dois métodos de médias móveis:

| Método | Entrada | Stop e alvo |
|---|---|---|
| SMA 20/50 com filtro 200 | Cruzamento de médias simples alinhado à tendência maior | Média lenta com buffer ATR; stop só aperta após candle encerrado; alvo inicial pode crescer 25% em tendência forte |
| EMA 9/21 com filtro 50 | Retomada da média rápida com alinhamento das médias | Média lenta com buffer ATR, limite de afastamento e alvo por múltiplos do risco |

As regras são próprias e explicáveis. Métodos conhecidos não recebem aprovação automática. Referências: [exemplo LEAN de médias](https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/MovingAverageCrossAlgorithm.py), [walk-forward](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization) e [estudo de Brock, Lakonishok e LeBaron](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x). O estudo histórico não prova vantagem hoje.

## Metas e perdas: duas rodadas limitadas

Foram avaliadas 234 combinações no desenvolvimento: 108 combinações amplas e nove refinamentos por perfil temporal. Seis métodos, alvos de 1,5/2/3 R, stops de 1/2 ATR e três perfis financeiros. O refinamento variou alvo/stop em 0,25, usando somente desenvolvimento.

| Perfil | Risco por operação | Perda diária | Meta diária |
|---|---:|---:|---:|
| Conservador | 0,25% | 1% | 1% |
| Equilibrado | 0,5% | 2% | 2% |
| Maior risco, somente estudo | 1% | 3% | 3% |

Capital hipotético de 100.000 USDT, sem conversão para reais. Taxa assumida de 10 bps por lado (0,1%); stress dobra taxa e slippage. Reservas e unidades são premissas de pesquisa, não tarifas nem filtros oficiais da exchange. As configurações da sessão do usuário não foram substituídas.

## Avaliação externa com parâmetros congelados

Os testes anteriores (2024–2025 diário e setembro/2025 intradiário) foram retirados da avaliação externa e declarados desenvolvimento da segunda iteração. As janelas novas foram janeiro–setembro/2026 no diário e 1–15/outubro/2025 em cinco minutos, em BTCUSDT e ETHUSDT. O aquecimento contém somente candles anteriores ao teste, sem ordens.

| Série | Acerto referência | Acerto candidato | Operações candidato | Líquido referência USDT | Líquido candidato USDT |
|---|---:|---:|---:|---:|---:|
| BTCUSDT, diário | 40.0% | 28.6% | 7 | 2201.75 | -877.52 |
| ETHUSDT, diário | 57.1% | 50.0% | 6 | 3681.29 | 1776.92 |
| BTCUSDT, 5 min | 25.0% | 23.1% | 65 | -3588.05 | -9999.97 |
| ETHUSDT, 5 min | 52.9% | 23.6% | 55 | 940.66 | -4621.27 |

**Conclusão: os candidatos selecionados no desenvolvimento não superaram a referência de forma consistente na avaliação externa. Nenhum foi promovido automaticamente.** Há perdas, amostras diárias pequenas e degradação entre períodos. Acerto alto isoladamente não demonstra vantagem após custos. No intradiário, limites bloquearam novas entradas quando o orçamento de perdas se esgotou.

O cruzamento SMA teve zero operações em parte dos períodos; isso significa ausência de amostra, não acerto de 0% nem aprovação. Todos os resultados das médias e o stress estão no relatório JSON completo. Intervalos descritivos de expectativa por bootstrap em blocos acompanham os relatórios; não provam desempenho futuro.

## Simulações cegas e registro de decisões

Foram concluídas 81 execuções externas/adversas, com 143.332 decisões observadas, além das rodadas de desenvolvimento e testes automatizados.
O avaliador entregou um candle por vez ao motor, sem nome do cenário, próximo preço ou resultado esperado. Foram avaliados gaps, falta de candles, ausência de volume, wick extremo, falso rompimento e fluxo contrário. Casos artificiais são identificados como perturbações de dados reais.

Passaram as verificações aplicáveis de custos, permissão do ativo, risco inicial e cronologia. Um teste mudou somente o futuro e manteve todas as decisões anteriores iguais. Gaps podem produzir perdas maiores que o stop planejado; o teste não presume proteção perfeita. Sinais, números, bloqueios, ordens e saídas estão em arquivos de decisões. Isso descreve regras observadas, não consciência ou raciocínio humano.

## Memória e renovação dos históricos

- `runtime/aprendizado/memoria_treinamento.jsonl`: treino, validação e políticas congeladas, com sequência e cadeia de hashes.
- `runtime/aprendizado/avaliacoes_cegas.jsonl`: avaliações externas, excluídas das sugestões de parâmetros para treinar.
- `runtime/aprendizado/datasets/` e `models/`: quatro conjuntos de treino e seus modelos arquivados localmente; novos treinos pela interface também são preservados.
- `runtime/aprendizado/historicos_utilizados.json`: controla janelas de desenvolvimento e avaliação. Sobreposição é recusada para uma avaliação nova.
- Até três configurações escolhidas no treino anterior podem iniciar o próximo estudo como candidatas; precisam ser avaliadas novamente no desenvolvimento novo. Resultados cegos não alimentam essa seleção.
- O próximo ciclo escolhe janelas móveis e baixa dados novos; cada execução tem uma pasta própria. Um perfil sem histórico inédito suficiente aguarda e permite que outro perfil prossiga. Não existe retreino agendado ou processo de treino infinito nesta entrega.

Na conferência atual há uma janela intradiária nova de 14–20/outubro/2026 disponível para o próximo ciclo, com treino anterior. O perfil diário aguarda mais dados inéditos. Repetir períodos conhecidos só é permitido como regressão, sem chamar isso de validação independente.

## Verificação e uso

- 101 testes automatizados, compilação dos módulos e teste da interface.
- Teste da interface inclui treino de modelo enriquecido, memória local, backup e restauração.
- `python -m scripts.benchmark_engine --durable` compara o caminho antigo de persistência; sem o argumento usa o estado descartável.
- `python -m scripts.research_goals --plan-only` mostra as próximas janelas disponíveis.
- `python -m scripts.research_goals` executa um novo ciclo limitado, com duas CPUs e rotação de histórico.
- `--fixed-history` repete o protocolo original somente para regressão. Não produz evidência inédita.

As fontes novas usam os endpoints públicos de candles da [Binance](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md), com atividade do candle encerrado; brapi, Mercado Bitcoin e CVM continuam disponíveis. Não reconstruímos livro histórico a partir de candles nem incluímos balanços atuais em previsões passadas. A [comparação de projetos GitHub](GITHUB_ENGINE_COMPARISON.md) detalha as referências.

Os arquivos completos ficam localmente em `reports/engine-upgrade/`: benchmarks, protocolos, matrizes CSV, modelos, datasets, decisões e sumários. Os estudos não validam WIN/WDO ou integração com corretora real.
