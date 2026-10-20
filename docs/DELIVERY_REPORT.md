# Relatório de entrega — PULSE-TRADER 2.0

Data: 20/10/2026. Execução financeira: exclusivamente PAPER.

## Implementado

Domínio modular em `trading_assistant/v2`: dados CSV/sintéticos, validação OHLCV, cache SQLite,
agregação de candles completos, indicadores, três estratégias explicáveis, filtro multitemporal,
limites financeiros, ordens idempotentes, posição persistente, custos, latência, IOC parcial,
stops conservadores, gaps, trailing/break-even e emergência persistente.

Backtest reproduzível por ativo com hashes, parâmetros, equity, drawdown, resultados por regime,
benchmark simples, particionamento temporal, walk-forward e sensibilidade. ML opcional com
normalização somente no treino, purge temporal, baselines, checksum e aviso de drift;
não calibra confiança nem pode ignorar o risco ou ativar execução.

Dashboard desktop com Tk/CustomTkinter opcional, candles, volume, EMA9/21, zoom, navegação,
timeframes, temas, sinais, resultados, controles simples de risco/estratégia e JSON avançado.
Entradas pendentes são canceladas ao detectar candles ausentes; stops abertos continuam ativos no replay.
Scripts Windows para venv, inicialização e diagnóstico; `iniciar.cmd` abre o aplicativo.
O modo básico da instalação cria venv sem pip: o núcleo não precisa de pacotes externos.

## Correções no código anterior

Desativado roteamento legado que ignorava risco persistente; LIVE lança erro.
Corrigidos dimensionamento por multiplicador/lote, aumento indevido por confiança,
contagem de recomendações como operações, viés vendedor da penalidade de notícias,
timestamps sintéticos e serialização/redação de segredos na auditoria.
A UI anterior e módulos de notícias/análise foram preservados, sem execução de ordens por esse caminho.

## Verificação efetiva

- 47 testes unitários/integração aprovados, sem skips, incluindo injeção de falha e rollback.
- Compilação de todos os módulos aprovada.
- Smoke da interface Windows: formulário de risco, 80 candles, renderização, zoom, pan, tema, timeframe e emergência aprovados.
- Diagnóstico Python 3.12.10 / SQLite 3.49.1 / Tk aprovado.
- Venv criado e diagnóstico do instalador aprovado.
- Demo de 1.000 candles, walk-forward de 500, treino ML de 300 e sensibilidade executados.
- CSV exportado/reimportado produz relatório idêntico no teste end-to-end.
- Histórico original do Git recuperado com os 17 commits; integridade verificada.

Não há validação de rentabilidade. O modelo sintético de exemplo ficou abaixo de baselines no holdout;
nenhum modelo foi promovido a execução. Relatórios locais são exemplos de mecânica, não recomendações.

## Pendências e limites conhecidos

Rico/Profit: fronteira bloqueada e documentada. Sem SDK oficial, licença, sandbox ou confirmação de
habilitação da conta Rico. Não foi implementada uma falsa integração. Custos externos não foram
cotados ou contratados. Feed autorizado em tempo real depende dessas permissões/dados.

Sem calendário oficial B3 completo, rolagem automática, sincronização de portfólio multativo,
leilões/haltes, fila real, ajuste diário completo de futuros ou tributação. Margens/taxas são premissas.
As proteções são locais ao replay e param se o programa fechar. Gaps podem superar o risco planejado.

Instalação de bibliotecas extras falhou por DNS; fallback Tk foi testado, CustomTkinter não.
Empacotamento `.exe` foi avaliado, mas não construído sem dependências/PyInstaller.
Backtest extenso pode bloquear a janela; use CLI para séries longas.

## Instalar/executar

Na pasta do projeto: `python main.py`, ou clique em `iniciar.cmd`.
Ambiente isolado: `.\scripts\install.ps1` e `.\scripts\start.ps1`.
`README.md` contém instruções de CSV, limites, CLI, recuperação e fontes oficiais.

## Entrega Git

Branch solicitada: `feature/pulse-trader-v2`; `main` preservada.
Publicação por conector GitHub, pois clone/push direto falhou por DNS.
Commits de implementação, interface/Windows e documentação/testes preparados separadamente.
Pull Request de revisão sem merge automático, conforme acesso disponível.

## Pasta local

A cópia editável desta entrega está em `C:\Users\A1\Documents\ChatGPT\pulse`.
A pasta antiga em `C:\Users\A1\Documents\Codex\2026-10-20\new-chat\PULSE-TRADER` não recebe automaticamente
essas modificações. O PR contém o código para revisão; não houve merge em `main`.
