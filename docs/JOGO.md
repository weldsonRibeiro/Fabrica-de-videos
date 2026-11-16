# O jogo

> "Não é só um jogo, é criar conteúdo e monetizar enquanto se diverte."

## Núcleo (já implementado em `fabrica/jogo.py`)

- **Cada vídeo produzido = despesa da empresa.** O custo real das etapas (IA, voz, imagem) é
  debitado da carteira.
- **Cada view = moeda.** Taxa inicial: **10 moedas / 1.000 views** (`MOEDAS_POR_MIL_VIEWS`).

## Ideias para evoluir

- **O escritório** ✅ *(pixel art vista de cima, tela inicial do painel)*: uma sala por canal, agentes que andam entre as estações de cada etapa, sala de descanso e sala do Maestro. Próximos passos do visual: decoração/upgrades comprados com moedas (e o nível da sala vindo deles), mais de um agente por canal (um por vídeo em paralelo), agentes que vão até a sala do Maestro entregar o vídeo, moedas caindo no cofre quando as views entram, a "Loja" como sala própria.
- **Lojas**: negócios paralelos dentro do jogo que geram renda passiva e financiam a fábrica.
- **Missões**: tarefas diárias (aprovar X vídeos, bater meta de views) que dão bônus.
- **Upgrades**: comprar provedores melhores (voz mais natural, mais cenas, mais canais) com as moedas.
- **Novos canais**: desbloquear canais conforme o saldo cresce.
- **Ranking/temporadas**: comparar desempenho entre canais e entre jogadores.

## Cuidado de design

A moeda do jogo deve refletir resultado real (views), mas o jogo não deve incentivar spam de
vídeos de baixa qualidade: considerar retenção/engajamento além de views brutas ao refinar a economia.
