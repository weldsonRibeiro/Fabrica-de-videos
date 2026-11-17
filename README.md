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

## Como rodar

```bash
git clone https://github.com/weldsonRibeiro/Fabrica-de-videos && cd Fabrica-de-videos
./scripts/iniciar.sh --demo        # vê o painel e o escritório em 1 minuto, sem chaves
./scripts/iniciar.sh               # modo real (cria .env e canais.json; o `doctor` diz o que falta)
docker compose up -d --build       # ou: 24 h num servidor/PC com Docker
```

Passo a passo completo (chaves, YouTube, Docker, **Railway**, painel na **Vercel**, celular, primeiro vídeo de teste): **[docs/DEPLOY.md](docs/DEPLOY.md)**.

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
├── demo.py         # dados de demonstração (um dia inventado)
├── painel.py       # painel web (+ web/: index.html, escritorio.js, escritorio-motor.js)
├── doctor.py       # `fabrica doctor`: o que falta antes de rodar
├── env.py / fuso.py # .env automático; relógio no fuso do dono
├── cli.py          # linha de comando
└── provedores/
    ├── base.py     # contratos: Provedor, Publicador, LimiteAtingido
    ├── youtube.py  # publicação: upload resumível, thumbnail, shorts, agendamento, OAuth
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
python -m fabrica painel                   # painel de aprovação (veja abaixo)
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

### Publicação no YouTube (v0.3)

```bash
python -m fabrica youtube-autorizar --canal historias    # uma vez por canal; imprime o refresh token p/ o .env
python -m fabrica --provedor real --publicador youtube tick
```

- O vídeo sobe como **privado com `publishAt`** no horário que você aprovou (fuso `FABRICA_FUSO`, padrão `America/Sao_Paulo`); o YouTube o publica sozinho. Horário já passado vira "agora + 10 min".
- Sobem juntos a **thumbnail escolhida** e os **shorts** (cada um agendado `FABRICA_INTERVALO_SHORTS_H` horas depois do anterior, com link para o vídeo completo).
- **Selo de conteúdo sintético** (`containsSyntheticMedia`) vem ligado: narração e imagens são geradas por IA e o YouTube exige a declaração.
- **Upload resumível**: se cair no meio, a próxima batida continua do byte onde parou; vídeo, thumbnail e cada short são gravados em `saida/<vídeo>/publicacao.json`, então nada sobe duas vezes.
- **Cota da API**: cada upload gasta 1.600 das 10.000 unidades diárias (≈ 6 uploads/dia, shorts contam). Estourou? O vídeo continua *aprovado* e é tentado de novo após a virada da cota (00:00 do Pacífico). Para mais canais/shorts, peça aumento de cota ao Google.
- ⚠️ **Verifique antes de depender disso**: projetos novos da API que não passaram pela auditoria do YouTube podem ter os vídeos enviados **travados como privados** (o agendamento não os libera). Teste com um vídeo e, se for o caso, solicite a auditoria. Thumbnails personalizadas exigem canal verificado.
- Como o resto, foi testado com um YouTube simulado (upload em pedaços, retomada, cota, OAuth local), **não contra a API real**.

### Painel de aprovação no celular (v0.4)

```bash
export FABRICA_PAINEL_CHAVE=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
python -m fabrica --provedor real --publicador youtube painel --com-maestro
# abra uma vez: http://127.0.0.1:8080/?k=<a chave>   (a chave vira cookie e some da URL)
```

- Cada vídeo pronto aparece como um cartão: **player do vídeo, 3 títulos, 3 thumbnails, shorts e o horário** (sugestão: amanhã às 18h). Um toque em **Aprovar e agendar** e o maestro sobe na próxima batida.
- Lista **"Na fábrica"** com o status de cada vídeo (produzindo, pausado até quando, aguardando você, agendado, falhou) e o **saldo** do jogo no topo. Atualiza sozinho a cada 30 s sem perder o que você já escolheu.
- `--com-maestro` roda o tick a cada 60 s no mesmo processo (um comando só); sem ele, use o `tick` no cron.
- **Segurança**: chave obrigatória (≥ 16 caracteres), cookie `HttpOnly`/`SameSite=Strict`, aprovação exige cabeçalho próprio (anti-CSRF), só serve arquivos de dentro de `saida/`, textos da IA nunca entram como HTML. Escuta em `127.0.0.1`; para abrir no celular fora de casa, publique **atrás de HTTPS** (túnel tipo Cloudflare Tunnel/Tailscale ou proxy reverso) — não exponha a porta em HTTP puro.
- Vídeo com suporte a `Range` (necessário para tocar no Safari/iOS).

### O escritório (visual do jogo)

```bash
python -m fabrica --dados dados-demo --canais canais-demo.json demo      # cria um dia inventado (sem chaves, sem gastos)
FABRICA_PAINEL_CHAVE=<16+ caracteres> python -m fabrica --dados dados-demo --canais canais-demo.json painel
```

A tela inicial do painel é o **escritório em pixel art, visto de cima**, tela cheia, com os dados reais da fábrica:

- **Uma sala por canal** (piso de cor própria, com o nome e o nível "Nv"), mais a **Sala de descanso** (onde você aparece, de terno) e a **Sala do Maestro** (agenda do dia no quadro, caixa de aprovação e cofre).
- **Cada canal tem um agente** que **anda até a estação da etapa em andamento**: 📚 estante (pesquisa) → ✍️ mesa (roteiro, sentado) → 🎙️ cabine (narração, com ondas de voz) → 🖼️ cavalete (cenas, rabiscando) → 🎞️ computador (montagem, linha do tempo) → 🎨 mesa de arte (thumbnail). Fora do trabalho, passeia pela sala.
- **Balões**: `…` pensando/trabalhando, ⏳ pausado (limite da IA; retoma sozinho), ✓ vídeo pronto esperando você, `!` para você quando há aprovações.
- **HUD**: saldo de moedas, ganho por hora (views das últimas 24 h), gasto de hoje e o botão amarelo **Painel**.
- **Câmera**: arraste para mover, pince (ou role o mouse) para dar zoom, toque no nome de uma sala para aproximar, toque num agente para ver o que ele faz (etapa, tema, progresso) e toque na caixa de aprovação para ir aprovar.
- **Painel** (botão amarelo): *Aprovar*, *Agenda* (Maestro ligado/parado, próximas produções, a semana), *Canais* (perfis), *Caixa* (extrato) e *Fábrica* (linha de produção e todos os vídeos).
- Tudo é desenhado em canvas (sem imagens) em `fabrica/web/escritorio.js` (peças) e `escritorio-motor.js` (agentes e câmera). Respeita "reduzir movimento".
- O **nível da sala** é provisório: 1 + (vídeos agendados no canal ÷ 3). Dá para trocar a regra quando os upgrades do jogo existirem.

Os canais ficam em [`canais.example.json`](canais.example.json) (nome, nicho, horário de início,
lista de temas e um **perfil** opcional: voz, tom, público, estilo visual, o que evitar, nº de cenas e
categoria do YouTube — veja `docs/DEPLOY.md`). `canais.gta6.json` é um exemplo pronto com 6 canais sobre o lançamento de GTA 6.

## Como a "retomada sozinha" funciona

Cada etapa concluída é gravada na hora (checkpoint). Se o provedor levanta `LimiteAtingido`, o
vídeo vira `pausado` com um `retomar_em`; a próxima batida do maestro depois desse horário continua
**da etapa que faltava**. Falhas comuns têm até 3 tentativas antes de virar `falhou`.

## Roadmap

- [x] **Provedores reais** — Claude (pesquisa/roteiro), TTS, imagem, montagem (ffmpeg) — *falta validar contra as APIs reais*
- [x] **Publicação real** — YouTube Data API: upload agendado + shorts — *falta validar contra a API real*
- [x] **Painel de aprovação** — web mobile para escolher título, thumbnail e horário em 1 toque (falta: recusar/refazer, notificação)
- [ ] **Notificação** — avisar no celular quando um vídeo ficar pronto
- [ ] **Métricas reais** — puxar views do canal e converter em moedas automaticamente
- [x] **Escritório visual** — estações, funcionários, agenda, cofre e extrato (aba Escritório do painel)
- [ ] **O jogo de verdade** — lojas, missões, upgrades que melhoram a fábrica
- [ ] **Agenda inteligente** — temas gerados pela própria IA a partir de tendências e desempenho
- [x] **Execução contínua** — Dockerfile, docker-compose, Railway, `doctor`, `/saude` (falta: alertas e deploy testado em produção)

Detalhes de arquitetura e do design do jogo em [`docs/`](docs/).

## Mesa de operações (Bitcoin) — laboratório de simulação

Módulo separado (`mesa/`) para pesquisar operações com **agentes leitores, probabilidades calibradas e risco**, só em **simulação** (não envia ordens a corretoras). Veja [`docs/MESA.md`](docs/MESA.md) o passo a passo para o computador em [`docs/MESA_COMPUTADOR.md`](docs/MESA_COMPUTADOR.md) e o **caderno de pesquisa com os resultados** em [`docs/RESULTADOS.md`](docs/RESULTADOS.md).

```bash
python -m mesa sintetico --modo ruido --saida x.csv && python -m mesa backtest --dados x.csv   # testa a estrutura
python -m mesa baixar --saida btc.csv && python -m mesa backtest --dados btc.csv                # com Bitcoin real (no seu computador)
python -m mesa vigiar                                                                            # monitora o Bitcoin 24 h com dados reais e opera NA SIMULAÇÃO
python -m mesa coletar --fonte binance && python -m mesa curto --dados btc1m.csv                 # curto prazo: coletor 24 h e teste H2 (custo de equilíbrio)
```

## Origem da ideia

Ideia vinda de um seguidor — o relato de "um dia inteiro da fábrica de vídeos com IA" que inspirou
este projeto. Veja o texto original em [`docs/IDEIA.md`](docs/IDEIA.md).
