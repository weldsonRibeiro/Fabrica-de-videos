# O jogo

> "Não é só um jogo, é criar conteúdo e monetizar enquanto se diverte."

## Núcleo (já implementado em `fabrica/jogo.py`)

- **Cada vídeo produzido = despesa da empresa.** O custo real das etapas (IA, voz, imagem) é
  debitado da carteira.
- **Cada view = moeda.** Taxa inicial: **10 moedas / 1.000 views** (`MOEDAS_POR_MIL_VIEWS`).

## Ideias para evoluir

- **O escritório** ✅ *(v0.5, aba Escritório do painel)*: cada etapa do pipeline é uma estação — estante
  (pesquisa), mesa (roteiro), cabine (narração), quadro (cenas), computador (montagem), cavalete
  (thumbnail) — e cada vídeo em produção é um funcionário que anda entre elas. Próximos passos do
  visual: decoração/upgrades comprados com moedas, um funcionário por canal fixo, animação de moedas
  caindo no cofre quando as views entram.
- **Lojas**: negócios paralelos dentro do jogo que geram renda passiva e financiam a fábrica.
- **Missões**: tarefas diárias (aprovar X vídeos, bater meta de views) que dão bônus.
- **Upgrades**: comprar provedores melhores (voz mais natural, mais cenas, mais canais) com as moedas.
- **Novos canais**: desbloquear canais conforme o saldo cresce.
- **Ranking/temporadas**: comparar desempenho entre canais e entre jogadores.

## Cuidado de design

A moeda do jogo deve refletir resultado real (views), mas o jogo não deve incentivar spam de
vídeos de baixa qualidade: considerar retenção/engajamento além de views brutas ao refinar a economia.
