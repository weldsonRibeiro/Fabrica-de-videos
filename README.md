# 🏭 Fábrica de Vídeos

> Um dia inteiro de uma fábrica de vídeos com IA — e quase tudo acontece sem eu encostar.

Uma fábrica que **agenda, pesquisa, escreve, narra, ilustra, monta e publica** vídeos para vários
canais, com o dono só **aprovando**. E por cima disso, um **jogo**: cada vídeo produzido vira
despesa da empresa, e cada view vira moeda. Não é só um jogo — é criar conteúdo e monetizar
enquanto se diverte.

## Um dia na fábrica

| Quando | Quem | O que acontece |
|---|---|---|
| Madrugada | 🎼 **Maestro** | Monta a agenda: cada canal com o vídeo do dia, cada um no seu horário. |
| 05:30 | 🏭 **Agente da sala** | Sai o primeiro vídeo. Vai à estante e **pesquisa** o tema → senta e escreve o **roteiro** → entra na cabine e grava a **narração** → desenha as **cenas** no quadro → **monta** o vídeo no computador → faz a **thumbnail**. |
| Qualquer hora | ♻️ **Retomada** | Se a IA trava ou bate no limite do dia, a fábrica espera e **retoma sozinha de onde parou** (sem refazer — nem pagar de novo — as etapas já prontas). |
| Quando fica pronto | 📬 **Caixa de aprovação** | Chega pro dono o vídeo com **shorts, thumbnails e opções de título**. |
| Dono, na rua | 👤 **Você** | Escolhe título, thumbnail e **horário**, e aprova. Só isso. |
| Depois | 🚀 **Publicação** | O vídeo sobe sozinho, **agendado**. |
| Sempre | 🎮 **Jogo** | Cada vídeo vira **despesa** da empresa; cada view vira **moeda**. Enquanto isso o dono cuida das lojas e faz missão. |
| À noite | 🌙 **Maestro** | O dia seguinte já está na agenda. O escritório não para. |

## O que já existe (v0.1 — esqueleto funcional)

A fábrica inteira já roda de ponta a ponta com **provedores falsos** (não gasta nada), para validar
o fluxo antes de ligar as IAs de verdade.

```
fabrica/
├── modelos.py      # Canal, Vídeo, Etapas, Status
├── maestro.py      # agenda do dia (+ do dia seguinte à noite), relógio da fábrica, aprovação, publicação
├── pipeline.py     # pesquisa → roteiro → narração → cenas → montagem → thumbnail, com checkpoint
├── config.py       # configuração por variáveis de ambiente
├── jogo.py         # carteira: vídeo = despesa, view = moeda (idempotente)
├── armazem.py      # estado em JSON, escrita atômica (sobrevive a travas e reinícios)
├── cli.py          # linha de comando
└── provedores/
    ├── base.py     # contratos: Provedor, Publicador, LimiteAtingido
    ├── real.py     # provedor real (compõe claude.py, openai_http.py, montagem.py)
    └── falso.py    # provedores de mentirinha para demo e testes
```

### Rodando

Requer só Python 3.10+ (sem dependências).

```bash
python -m unittest -v                      # testes

python -m fabrica agenda                   # monta a agenda de hoje (canais.example.json)
python -m fabrica tick                     # uma batida do maestro (rode a cada minuto via cron)
python -m fabrica status                   # lista os vídeos e em que etapa estão
python -m fabrica aprovar 2026-11-16-historias --titulo 1 --thumbnail 0 --publicar-em 2026-11-17T18:00
python -m fabrica tick                     # sobe e agenda o aprovado
python -m fabrica views 2026-11-16-historias 5000   # views viram moedas
python -m fabrica carteira                 # saldo da empresa
```

### Provedores reais (v0.2)

```bash
pip install '.[real]'                 # SDK do Claude (único extra); ffmpeg precisa estar no PATH
cp .env.example .env                  # preencha ANTHROPIC_API_KEY e OPENAI_API_KEY
set -a; source .env; set +a
python -m fabrica --provedor real tick
```

| Etapa | Quem faz | Como |
|---|---|---|
| Pesquisa | Claude | busca na web (`web_search`), dossiê com fontes |
| Roteiro | Claude | saída estruturada (JSON): cenas, 3 títulos, descrição, 3 ideias de thumbnail, 3 shorts |
| Narração | OpenAI TTS | um áudio por cena (a duração real de cada áudio dita o tempo da cena) |
| Cenas | OpenAI Images | uma imagem por cena |
| Montagem | ffmpeg | zoom lento por cena → vídeo 1080p; shorts 9:16 com fundo desfocado |
| Thumbnail | OpenAI Images + ffmpeg | 3 opções, 1280×720 JPG |

- **Modelo do Claude**: `claude-opus-5-5` por padrão; troque com `FABRICA_MODELO` (ex.: `claude-sonnet-5-5` para gastar menos).
  O *fallback* server-side do Claude vem ligado (se uma resposta for recusada, outro modelo refaz); desligue com `FABRICA_SEM_FALLBACK=1`.
- **Limites**: 429 do Claude ou da OpenAI viram pausa com horário de retomada (respeita `retry-after`).
- **Sem pagar duas vezes**: áudios e imagens já gerados ficam em disco e não são refeitos na retomada; o gasto parcial de uma etapa interrompida é guardado e somado quando ela termina.
- **Custos são estimativas** (tokens × tabela de preços do Claude; voz e imagem por valores configuráveis em `FABRICA_CUSTO_VOZ_MIN` e `FABRICA_CUSTO_IMAGEM`). Em USD; use `FABRICA_COTACAO` para converter.
- ⚠️ A integração com Claude/OpenAI foi testada com clientes simulados e o ffmpeg com arquivos de verdade; **ainda não rodou contra as APIs reais** (não havia chaves no ambiente de desenvolvimento). Rode o primeiro vídeo acompanhando.

Os canais ficam em [`canais.example.json`](canais.example.json) (nome, nicho, horário de início e
lista de temas).

## Como a "retomada sozinha" funciona

Cada etapa concluída é gravada na hora (checkpoint). Se o provedor levanta `LimiteAtingido`, o
vídeo vira `pausado` com um `retomar_em`; a próxima batida do maestro depois desse horário continua
**da etapa que faltava**. Falhas comuns têm até 3 tentativas antes de virar `falhou`.

## Roadmap

- [x] **Provedores reais** — Claude (pesquisa/roteiro), TTS, imagem, montagem (ffmpeg) — *falta validar contra as APIs reais*
- [ ] **Publicação real** — YouTube Data API: upload agendado + shorts
- [ ] **Painel de aprovação** — app/web mobile para escolher título, thumbnail e horário em 1 toque
- [ ] **Notificação** — avisar no celular quando um vídeo ficar pronto
- [ ] **Métricas reais** — puxar views do canal e converter em moedas automaticamente
- [ ] **O jogo de verdade** — lojas, missões, escritório visual, upgrades que melhoram a fábrica
- [ ] **Agenda inteligente** — temas gerados pela própria IA a partir de tendências e desempenho
- [ ] **Execução contínua** — rodar o maestro num servidor (cron/worker), com logs e alertas

Detalhes de arquitetura e do design do jogo em [`docs/`](docs/).

## Origem da ideia

Ideia vinda de um seguidor — o relato de "um dia inteiro da fábrica de vídeos com IA" que inspirou
este projeto. Veja o texto original em [`docs/IDEIA.md`](docs/IDEIA.md).
