# Plano de desenvolvimento e situação

| Fase | Entregue | Limitação externa ou próxima etapa |
|---|---|---|
| Auditoria | Inventário dos 43 arquivos, achados, arquitetura e branch isolada | Clone por DNS substituído por obtenção via conector |
| Dados | Protocolo de provedor, CSV validado, sintético determinístico, agregação, cache SQLite | Sem feed autorizado em tempo real; sem rolagem/calendário oficial |
| Análise | 3 estratégias, indicadores, validade, motivos, filtro multitemporal | Confiança calibrada indisponível |
| IA | Regressão logística opcional, treino temporal com purge, baselines, checksum e drift | Sem adoção automática; não validada em dados reais |
| Risco | Valores financeiros por contrato, custos, limites persistentes, exposição, margem e emergência | Margens/tarifas informadas pelo usuário; gaps podem exceder stops |
| Paper | Ordens únicas, estados, fills parciais IOC, custos, latência, stops e recuperação | Liquidez aproximada; não simula fila/leilão |
| Rico/Profit | Pesquisa oficial e interface bloqueada com testes | Falta licença, SDK, confirmação da Rico e sandbox |
| Dashboard | Canvas, candles, volume, EMA, zoom, timeframes, temas, configurações, resultados | Tk fallback testado; CustomTkinter indisponível no ambiente |
| Backtest | Reprodutível, hash, custos, gaps, equity, regimes, baseline, walk-forward e sensibilidade | Um ativo por vez; resultados sintéticos não são evidência de mercado |
| Qualidade | Suíte unitária/integração, falhas injetadas e smoke da interface | Mais homologação operacional necessária antes de qualquer integração real |
| Windows | Inicialização, instalação venv, diagnóstico, variáveis de ambiente | `.exe` avaliado e adiado por falta de dependências/rede |
| GitHub | Commits na branch de desenvolvimento e PR sem merge, conforme disponibilidade | Ver relatório de entrega para os identificadores efetivamente criados |

Decisões: preservar código anterior, isolar o domínio novo, eliminar caminhos de execução que ignorem risco,
não instalar serviços pagos, usar SQLite transacional e dependências opcionais.

Melhorias futuras: feed oficial, registro completo dos contratos e calendário B3, portfólio sincronizado,
validação fora da amostra em histórico licenciado, desempenho estatístico com intervalos de confiança,
interface configurável por formulários e empacotamento assinado. Nenhuma dessas etapas habilita REAL nesta versão.
