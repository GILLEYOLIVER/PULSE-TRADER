# Segurança

Não há envio real de ordens nem carregamento de DLL de trading. `RicoProfitAdapter` lança PermissionError
em envio, cancelamento, consulta ou reconciliação. O roteador legado rejeita LIVE e não executa ordens.
Nenhuma variável de ambiente ativa negociação real.

Não inserir senhas da Rico. Chaves opcionais de notícias ficam no ambiente e são redigidas na auditoria.
O logger anterior foi corrigido para serializar datetime e não engolir falhas de gravação.
O SQLite local contém somente estado de simulação; não é cofre de credenciais, nem log resistente a adulteração.

SQLite usa transações IMMEDIATE, journal WAL e synchronous FULL. Falhas durante execução geram rollback;
se abrir, validar ou gravar o estado falhar, o erro se propaga e novas operações não são produzidas.
IDs de ordens são persistentes. Dados inválidos, sem timezone, revisados ou fora de ordem são rejeitados.
Não há desserialização pickle ou avaliação de código em configuração JSON/modelos.

A UI usa SQLite online backup, hashes e verificação de integridade, com restauração em diretório vazio.
Nenhum servidor ou instalação de SQLite é necessário. Restaurar uma cópia antiga também restaura
seu relógio e limites de simulação; não usar esta ferramenta para contabilizar uma conta real.
Não apagar runtime para esconder perdas. Estados de emergência continuam após reiniciar.
O bloqueio depende do relógio de replay, não de cotações reais ou proteções hospedadas na corretora.
O calendário opcional é fornecido pelo usuário; `verified: true` não prova que datas e horários são oficiais.
Um calendário incompleto pode admitir entradas em períodos em que a B3 não negocia.

Dependências opcionais devem ser revisadas e travadas antes de distribuição externa. CustomTkinter e Pillow
foram instalados para o teste local; uma auditoria de vulnerabilidades e assinatura do pacote ainda faltam.
O núcleo novo usa stdlib.

Consultas de mercado são de leitura em domínios de provedores documentados. `BRAPI_TOKEN` é lido
do ambiente e não aparece nos arquivos de configuração, banco ou pacote. ZIPs CVM são lidos em memória,
sem extração de caminhos. Backups restaurados têm caminhos e hashes verificados antes da escrita.
Snapshots atuais de fundamentos/modelos ficam fora de replays anteriores à sua disponibilidade.
