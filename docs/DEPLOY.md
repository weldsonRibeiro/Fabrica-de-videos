# Como rodar a fábrica

Três caminhos. Comece pelo **A** (5 minutos, sem chaves) para ver tudo funcionando; depois escolha **B** ou **C** para deixar rodando 24 h.

| | Onde roda | Bom para | Fica ligada sozinha? |
|---|---|---|---|
| **A** | Seu computador, direto | Testar, ver o painel | Só enquanto o computador estiver ligado |
| **B** | Docker (seu PC ou um servidor/VPS) | Uso real | Sim (`restart: unless-stopped`) |
| **C** | Railway | Uso real sem cuidar de servidor | Sim |
| **D** | Painel na **Vercel** + fábrica em B ou C | Endereço/HTTPS/domínio próprio para o celular | Sim (a fábrica fica no B ou C) |

> Enquanto isto não estiver na `main`, use a branch `claude/adoring-clarke-62go5q` (`git checkout claude/adoring-clarke-62go5q`).

---

## 0. As chaves (só para o modo real)

O modo de **simulação** não precisa de nada disso. Para produzir e publicar de verdade:

| O quê | Onde conseguir | Variável |
|---|---|---|
| Claude (pesquisa e roteiro) | console.anthropic.com → API keys | `ANTHROPIC_API_KEY` |
| Voz e imagens | platform.openai.com → API keys | `OPENAI_API_KEY` |
| YouTube | Google Cloud (passos abaixo) | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN_<CANAL>` |
| Painel | você inventa | `FABRICA_PAINEL_CHAVE` (≥ 16 caracteres) |

Gerar a chave do painel: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### YouTube (uma vez)
1. No [Google Cloud Console](https://console.cloud.google.com), crie um projeto e ative a **YouTube Data API v3**.
2. *Tela de consentimento OAuth*: tipo **Externo**. Adicione o seu e-mail como usuário de teste. **Passe o app para "Em produção"**: em modo *Teste* o Google expira o token de atualização em 7 dias e a fábrica pararia de publicar. (Para uso pessoal aparece um aviso de "app não verificado"; é o seu próprio app.)
3. *Credenciais* → Criar → **ID do cliente OAuth** → tipo **App para computador**. Copie o ID e o segredo.
4. **No seu computador** (precisa de navegador), para cada canal:
   ```bash
   export YOUTUBE_CLIENT_ID=... YOUTUBE_CLIENT_SECRET=...
   python -m fabrica youtube-autorizar --canal historias
   ```
   Entre com a conta **dona do canal**. O comando imprime `YOUTUBE_REFRESH_TOKEN_HISTORIAS=...` — guarde no `.env` (ou nas variáveis do servidor).
5. Os canais precisam ser **verificados** no YouTube para aceitar thumbnails personalizadas. Se o upload sair travado como privado mesmo com `publishAt`, o projeto da API pode precisar da auditoria do YouTube (veja o README).

### Seus canais e perfis
Copie `canais.example.json` para `canais.json` e edite: `id` (sem espaços), `nome`, `nicho`, `inicio_producao` (`HH:MM`, no seu fuso) e a lista de `temas` (um por dia, em rodízio).

Cada canal pode ter um **`perfil`** — a identidade que o diferencia dos outros. Tudo é opcional; o que ficar vazio usa o padrão:

| Campo | Para quê | Onde age |
|---|---|---|
| `voz` | voz da narração (`alloy`, `ash`, `ballad`, `coral`, `echo`, `fable`, `nova`, `onyx`, `sage`, `shimmer`, `verse`) | narração |
| `estilo_voz` | como falar ("calmo e grave, como documentário") | narração |
| `tom` | tom do texto ("didático e bem-humorado") | pesquisa e roteiro |
| `publico` | para quem é ("jovens de 18 a 35 anos") | pesquisa e roteiro |
| `evitar` | lista de assuntos/palavras que o canal não usa | pesquisa e roteiro |
| `estilo_visual` | prefixo aplicado a **toda** imagem e thumbnail ("ilustração flat colorida") — garante a mesma cara em todos os vídeos | cenas e thumbnails |
| `cenas` | nº de cenas por vídeo (1 a 30) | roteiro (e custo) |
| `categoria_youtube` | número da categoria (`27` Educação, `28` Ciência e tecnologia, `22` Pessoas e blogs, `20` Games...) | publicação |
| `idioma` | idioma no YouTube (padrão `pt-BR`) | publicação |

Exemplo (veja `canais.example.json`):
```json
{ "id": "financas", "nome": "Dinheiro Sem Medo", "nicho": "educação financeira",
  "inicio_producao": "07:00", "temas": ["Reserva de emergência"],
  "perfil": { "voz": "nova", "tom": "didático e bem-humorado", "publico": "jovens de 18 a 35 anos",
              "estilo_visual": "ilustração flat colorida, fundo limpo", "evitar": ["promessas de ganho garantido"],
              "cenas": 10, "categoria_youtube": "27" } }
```
**Shorts e a cota do YouTube.** `shorts` define quantos shorts sobem com cada vídeo (padrão 3; `0` = nenhum). A cota padrão da API (10.000 unidades/dia) comporta só ~6 uploads por dia, e cada short conta como um upload: com muitos canais, `shorts: 0` é o que cabe. O `doctor` avisa quando o total ultrapassa a cota; para ligar os shorts, peça aumento de cota ao Google.

**Exemplo pronto:** `canais.gta6.json` traz 6 canais com foco no lançamento de GTA 6, cada um com um ângulo diferente (notícias do dia, guias, lore, tecnologia, retrospectiva da série e checagem de boatos), horários, vozes e estilos visuais próprios e 14 temas. Para usar: copie o conteúdo para o `canais.json` (ou para `FABRICA_CANAIS_JSON` no servidor).

O `python -m fabrica doctor` valida os perfis. No servidor, o conteúdo inteiro do `canais.json` vai na variável `FABRICA_CANAIS_JSON`; o painel mostra cada canal e seu perfil na aba *Escritório*. Mudanças no perfil valem para os vídeos **ainda não produzidos** (cada vídeo guarda uma cópia do perfil do dia em que foi agendado).

---

## A. No seu computador

**Linux/macOS** (Python 3.10+; ffmpeg para o modo real):

```bash
git clone https://github.com/weldsonRibeiro/Fabrica-de-videos && cd Fabrica-de-videos
git checkout claude/adoring-clarke-62go5q

./scripts/iniciar.sh --demo      # dia inventado, sem chaves: abre o link do painel que ele imprime
```

Para valer: `./scripts/iniciar.sh`. Na primeira vez ele cria `.env` e `canais.json` de exemplo e para; preencha, rode de novo. Ele roda o **`doctor`** (lista o que falta, sem mostrar segredos) e sobe o painel com o maestro.

**Windows**: use o caminho **B** (Docker Desktop) ou o WSL com os mesmos comandos acima.

Comandos úteis, com o `.env` já preenchido:
```bash
python -m fabrica doctor         # o que falta antes de rodar?
python -m fabrica status         # vídeos e etapas
python -m fabrica carteira       # saldo do jogo
```

---

## B. Docker (seu PC ou um servidor)

```bash
cp .env.example .env             # preencha (veja a tabela acima)
cp canais.example.json canais.json   # edite

docker compose up -d --build
docker compose logs -f fabrica   # acompanhar
```

- O estado (vídeos, thumbnails, saldo) fica no volume `fabrica-dados` (`/data`). **Faça backup dele**; `docker compose down` não apaga, `down -v` apaga.
- Os canais: ou edite o arquivo dentro do volume, ou coloque o JSON inteiro em `FABRICA_CANAIS_JSON` no `.env` (uma linha só). Sem nenhum dos dois, ele usa os canais de exemplo e avisa nos logs.
- `FABRICA_PROVEDOR` e `FABRICA_PUBLICADOR` valem `real` e `youtube` no compose. Para só testar o painel: `FABRICA_PROVEDOR=falso FABRICA_PUBLICADOR=falso docker compose up -d`.
- O painel escuta só em `127.0.0.1:8080`. Para o celular, veja a seção abaixo.
- Atualizar: `git pull && docker compose up -d --build`.

---

## C. Railway

1. railway.com → **New Project → Deploy from GitHub repo** → `Fabrica-de-videos` (a branch com este código). Se aparecer *"User does not have access to the repo"*, instale o app do Railway no GitHub com acesso a este repositório (GitHub → Settings → Applications → Railway → Configure). O `railway.json` já manda construir pelo `Dockerfile` e usar `/saude` como verificação.
2. **Variables**: `FABRICA_PAINEL_CHAVE`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN_<CANAL>`, `FABRICA_PROVEDOR=real`, `FABRICA_PUBLICADOR=youtube`, `FABRICA_FUSO=America/Sao_Paulo` e `FABRICA_CANAIS_JSON` (o conteúdo do `canais.json`). Defina também **`PORT=8080`** (e, em *Networking*, o domínio apontando para a porta **8080**): assim a porta do app e a do domínio sempre batem.
3. **Volume**: adicione um volume ao serviço montado em **`/data`** — sem ele, tudo some a cada deploy. (O Railway não aceita `VOLUME` dentro do Dockerfile; por isso o volume é criado no próprio Railway.)
4. **Settings → Networking → Generate Domain**. Já vem com HTTPS. Abra `https://SEU-DOMINIO/?k=SUA_CHAVE`.
5. Mantenha **uma réplica só** (o maestro não foi feito para rodar em duas ao mesmo tempo).

---

## D. Painel na Vercel (fábrica em B ou C)

**A Vercel não roda a fábrica**: ela só executa funções curtas, não tem disco persistente nem ffmpeg, e a fábrica precisa de um processo ligado o tempo todo (maestro, vídeos de vários minutos, estado em disco). Então a divisão é:

- **Fábrica** → caminho **B** (Docker) ou **C** (Railway), com um endereço público **HTTPS**.
- **Vercel** → só a "porta de entrada" do celular: ela repassa tudo (inclusive os vídeos, com `Range`) para a fábrica. Vantagens: seu domínio, HTTPS e um endereço fixo; o servidor pode ficar escondido atrás dele.

Passo a passo:

1. Suba a fábrica (B ou C) e anote o endereço público, ex.: `https://minha-fabrica.up.railway.app`. Confirme que `https://…/saude` responde `{"ok": true}`.
2. Gere a configuração da Vercel:
   ```bash
   ./scripts/vercel-configurar.sh https://minha-fabrica.up.railway.app
   git add vercel/vercel.json && git commit -m "Painel na Vercel" && git push
   ```
   (O `vercel.json` só tem o endereço do servidor, não tem segredo.)
3. Na Vercel: **Add New → Project → importe o repositório → Root Directory: `vercel`** → Deploy. Sem build, sem variáveis. (Ou, pelo terminal: `cd vercel && npx vercel --prod`.)
4. Abra `https://SEU-PROJETO.vercel.app/?k=SUA_CHAVE` no celular e use *Adicionar à tela inicial*. Um domínio próprio pode ser adicionado em *Settings → Domains*.

Cuidados:
- O servidor da fábrica **continua acessível pelo endereço dele**; a chave do painel é o que protege os dois. Use uma chave forte e não divulgue o endereço do servidor.
- O vídeo passa pela Vercel (conta no tráfego de saída do seu plano). Para só conferir vídeos de alguns minutos é pouco, mas fique de olho.
- **Plano Hobby**: pelos termos da Vercel, é para uso **pessoal e não comercial**. Como o objetivo aqui é monetizar canais, confira os termos; o plano Pro é o indicado para uso comercial.
- Esta configuração é só um repasse de rotas e **não foi testada contra a Vercel** (não tenho como criar o deploy daqui). Se algo não abrir, teste primeiro o endereço direto do servidor.

---

## Abrir no celular

- **Railway / servidor com domínio HTTPS**: `https://SEU-DOMINIO/?k=SUA_CHAVE`. A chave vira cookie e some do endereço. No celular: menu do navegador → *Adicionar à tela inicial* para abrir como app.
- **Docker no seu PC**, sem expor nada: use o **Tailscale** (instale no PC e no celular, mesma conta) e abra `http://IP-DO-TAILSCALE:8080/?k=CHAVE` (troque `127.0.0.1:8080:8080` por `8080:8080` no compose); ou o túnel opcional `docker compose --profile tunel up -d` e pegue o endereço `https://….trycloudflare.com` em `docker compose logs tunel` (muda a cada reinício; público, protegido só pela chave).
- **Mesmo Wi-Fi**: `http://IP-DO-PC:8080/?k=CHAVE` (HTTP puro; só em rede de casa).

Nunca exponha o painel em HTTP puro na internet.

---

## Primeiro vídeo de teste (barato)

Antes de deixar rodando, produza **um** vídeo curto, acompanhando:

1. Um canal só, com `inicio_producao` `"00:00"` (já passou → o maestro começa na hora).
2. `FABRICA_CENAS=3` (vídeo de ~1,5 min, ~⅓ do custo) e, se quiser, `FABRICA_MODELO=claude-sonnet-5-5`.
3. Suba e olhe a aba **Escritório**: o funcionário anda pelas estações. No fim, o vídeo aparece em **Aprovar**.
4. Aprove com um horário daqui a uns 15 minutos e confira no YouTube Studio se ficou **agendado**.
5. Só então volte `FABRICA_CENAS` ao normal e coloque os canais reais.

Os custos mostrados no jogo são **estimativas**; confira o gasto real nos painéis da Anthropic e da OpenAI nos primeiros dias.

---

## Operação

- **Logs**: `docker compose logs -f fabrica` (ou a aba *Logs* do Railway). Erros do maestro aparecem como `[maestro] erro no tick: …`.
- **Limite do dia / queda de rede**: o vídeo fica *pausado* (funcionário dormindo) e retoma sozinho.
- **Cota do YouTube**: ≈ 6 uploads/dia na cota padrão (shorts contam).
- **Backup**: a pasta `/data` (`dados/` = estado e saldo, `saida/` = vídeos gerados).
- **Fuso**: `FABRICA_FUSO` (padrão `America/Sao_Paulo`) define o horário da agenda **e** dos horários que você aprova — não depende do fuso do servidor.

## Segurança

- `.env` nunca vai para o git (já está no `.gitignore`). Se uma chave vazar, gere outra.
- A chave do painel dá o poder de aprovar publicações: trate como senha.
- O painel só serve arquivos de dentro da pasta de saída e exige a chave em tudo, exceto `/saude` (que só responde `{"ok": true}`).

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `a chave do painel precisa ter pelo menos 16 caracteres` | `FABRICA_PAINEL_CHAVE` ausente/curta |
| Painel abre "não autorizado" | faltou o `?k=SUA_CHAVE` na primeira visita |
| `provedor real indisponível` | falta `OPENAI_API_KEY` ou `pip install '.[real]'` |
| `sem refresh token para o canal` | rode `youtube-autorizar` no seu PC e ponha o token nas variáveis |
| Publicação parou depois de ~7 dias | app do Google ainda em *Teste*: passe para *Em produção* e autorize de novo |
| Tudo some após um deploy | volume não montado em `/data` |
| Horários errados | `FABRICA_FUSO` |
