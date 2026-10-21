# Plano de desenvolvimento e situação

Situação atual do upgrade 2.1: [seis passos, verificação e resultados](UPGRADE_6_STEPS.md).

| Fase | Entregue | Limitação externa ou próxima etapa |
|---|---|---|
| Auditoria | Inventário dos 43 arquivos, achados, arquitetura e branch isolada | Clone por DNS substituído por obtenção via conector |
| Dados | CSV/Profit, brapi/Mercado Bitcoin somente leitura, sintético, agregação e SQLite | Sem feed oficial B3 em tempo real ou rolagem/calendário oficial completo |
| Análise | 3 estratégias, indicadores, validade, motivos, filtro multitemporal | Confiança calibrada indisponível |
| IA | Treino temporal, calibração condicional, baselines, drift e quatro estudos reais | Nenhum estudo inicial demonstrou evidência suficiente; sem adoção automática |
| Risco | Valores financeiros por contrato, custos, limites persistentes, exposição, margem e emergência | Margens/tarifas informadas pelo usuário; gaps podem exceder stops |
| Paper | Ordens únicas, estados, fills parciais IOC, custos, latência, stops e recuperação | Liquidez aproximada; não simula fila/leilão |
| Rico/Profit | Pesquisa oficial e interface bloqueada com testes | Falta licença, SDK, confirmação da Rico e sandbox |
| Dashboard | Sugestões, contexto, planos PAPER, formulários completos, gráfico e tarefas em segundo plano | Smoke local aprovado; homologação em outros dispositivos ainda necessária |
| Backtest | Hash, custos, gaps, portfólio sincronizado, walk-forward, sensibilidade e holdout | Exige séries sincronizadas; resultados não garantem vantagem futura |
| Qualidade | Suíte unitária/integração, falhas injetadas e smoke da interface | Mais homologação operacional necessária antes de qualquer integração real |
| Windows | Inicialização, venv, executável/ZIP portátil por commit e self-test | Assinatura e homologação em outro computador permanecem externas |
| GitHub | PR #1 integrado a `main` por solicitação do usuário; continuação na branch de desenvolvimento | Nova revisão necessária antes de outro merge |

Complemento 2.0.2: calendário de sessão fornecido e conferido pelo usuário na UI/CLI/backtest,
validação de origem/duração de CSV, contagens inteiras, séries de ML compatíveis e quantidade idempotente.
O calendário oficial continua dependente de fonte autorizada e conferência externa.

Complemento 2.0.1: controles simples de risco e estratégia na interface, com JSON avançado preservado;
ordens pendentes canceladas ao detectar lacunas de dados, sem interromper saídas protetivas simuladas.

Decisões: preservar código anterior, isolar o domínio novo, eliminar caminhos de execução que ignorem risco,
não instalar serviços pagos, usar SQLite transacional e dependências opcionais.

Backtest de portfólio sincronizado concluído para séries completas de mesmo intervalo.
Melhorias futuras: feed oficial, registro completo dos contratos e calendário B3,
validação fora da amostra em histórico licenciado, desempenho estatístico com intervalos de confiança,
interface configurável por formulários e empacotamento assinado. Nenhuma dessas etapas habilita REAL nesta versão.
