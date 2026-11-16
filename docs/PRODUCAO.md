# Do zero à produção real — passo a passo

Ordem pensada para **não gastar dinheiro nem publicar nada por engano** até você ter visto um vídeo bom.
Cada fase termina com um **✔ Pronto quando…** — só passe para a próxima quando isso for verdade.

> Estado de partida: a fábrica já está no ar em **simulação** (Railway + Vercel), sem custo. Falta: chaves de IA, o YouTube e os seus canais.

Resumo das fases: **1** contas de IA · **2** YouTube · **3** servidor · **4** vídeo de teste sem publicar · **5** publicar 1 vídeo de teste · **6** ligar os canais aos poucos · **7** rotina diária.

---

## Fase 1 — Contas e chaves de IA

### 1.1 Claude (pesquisa e roteiro)
1. Entre em **console.anthropic.com** e crie/entre na conta.
2. Em *Billing*, adicione crédito (comece com um valor pequeno, ex.: US$ 20).
3. Em *Limits* (ou *Settings → Limits*), defina um **limite mensal de gasto**.
4. Em *API Keys* → *Create Key*, nome `fabrica`. **Copie a chave (`sk-ant-…`)** agora: ela só aparece uma vez. Guarde num gerenciador de senhas.

### 1.2 OpenAI (voz e imagens)
1. Entre em **platform.openai.com**.
2. Em *Billing*, adicione crédito e, em *Limits*, um **limite mensal**.
3. Em *API keys* → *Create new secret key*. **Copie (`sk-…`)**.
4. As imagens usam o modelo `gpt-image-1`, que pode exigir **verificação da organização** (*Settings → Organization → General → Verify Organization*). Se der erro de acesso a imagens no primeiro teste, é isso.

> **Custo (ordem de grandeza, estimativa do próprio sistema):** US$ 1 a 2 por vídeo longo de 10–12 cenas → 6 canais por dia ≈ US$ 6 a 12/dia. Confira o gasto real nos painéis das duas empresas nos primeiros dias. Para gastar menos: `FABRICA_MODELO=claude-sonnet-5-5`, menos cenas por canal.

✔ **Pronto quando:** você tem as duas chaves guardadas e os dois limites de gasto definidos.

---

## Fase 2 — YouTube

### 2.1 Os canais
1. Crie os **6 canais** no YouTube (na conta Google dona; cada um como *canal de marca*, em *Trocar de conta → Criar canal*). Nomes sugeridos: GTA 6 Hoje, Guia GTA 6, Leonida Lore, GTA 6 Tech, Do Vice City ao Leonida, Mitos e Verdades GTA 6.
2. Em **youtube.com/verify**, verifique o telefone de cada canal (necessário para **thumbnails personalizadas** e vídeos longos).

### 2.2 Projeto no Google Cloud (uma vez só, serve para os 6 canais)
1. **console.cloud.google.com** → crie um projeto (ex.: `fabrica-videos`).
2. *APIs e serviços → Biblioteca* → procure **YouTube Data API v3** → **Ativar**.
3. *APIs e serviços → Tela de consentimento OAuth* (ou *Google Auth Platform*):
   - Tipo de usuário: **Externo**.
   - Preencha nome do app, e-mail de suporte e e-mail do desenvolvedor.
   - Em *Usuários de teste*, adicione o e-mail da conta dona dos canais.
   - **Publique o app (status "Em produção")**. Em modo *Teste* o Google expira o token em 7 dias e a publicação para de funcionar.
4. *Credenciais → Criar credenciais → ID do cliente OAuth* → tipo **App para computador**. Copie o **ID do cliente** e a **chave secreta**.

### 2.3 Autorizar cada canal (no SEU computador, com navegador)
Precisa de Python 3.10+. Não precisa instalar nada além do código:

```bash
git clone https://github.com/weldsonRibeiro/Fabrica-de-videos && cd Fabrica-de-videos
export YOUTUBE_CLIENT_ID="cole-aqui"
export YOUTUBE_CLIENT_SECRET="cole-aqui"      # Windows PowerShell: $env:YOUTUBE_CLIENT_ID="..."
python3 -m fabrica --canais canais.gta6.json youtube-autorizar --canal gta6-hoje
```
1. O comando mostra um link. Abra, **escolha a conta e, na lista, o CANAL certo** (confira o nome!) e autorize. Aviso de "app não verificado": *Avançado → continuar* (é o seu app).
2. Ele imprime uma linha `YOUTUBE_REFRESH_TOKEN_GTA6_HOJE=…`. **Copie.**
3. Repita para cada canal trocando `--canal`: `gta6-guia`, `gta6-lore`, `gta6-tech`, `gta6-historia-serie`, `gta6-mitos`. Cada um gera um token diferente.

### 2.4 Cota e auditoria (saiba antes de começar)
- Cota padrão: 10.000 unidades/dia ≈ **6 uploads**. Por isso os canais estão com **`shorts: 0`**. Para ligar shorts, peça aumento de cota ao Google (formulário de *YouTube API Services – Audit and Quota Extension*).
- Projetos novos da API **sem auditoria** podem ter vídeos enviados **travados como privados**. Se na Fase 5 o vídeo agendado não publicar sozinho, é isto: peça a auditoria.

✔ **Pronto quando:** você tem o ID/segredo do cliente e **6 tokens** (um por canal), cada um autorizado no canal certo.

---

## Fase 3 — Servidor (Railway)

1. Em **railway.com**, confira que a conta `ronaldocloud1@outlook.com` está com **plano pago ativo** (o teste gratuito acaba).
2. Projeto `fabrica-de-videos` → serviço `fabrica` → **Variables → Raw Editor** → cole (ajustando os valores):

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN_GTA6_HOJE=...
YOUTUBE_REFRESH_TOKEN_GTA6_GUIA=...
YOUTUBE_REFRESH_TOKEN_GTA6_LORE=...
YOUTUBE_REFRESH_TOKEN_GTA6_TECH=...
YOUTUBE_REFRESH_TOKEN_GTA6_HISTORIA_SERIE=...
YOUTUBE_REFRESH_TOKEN_GTA6_MITOS=...
```
3. **Não mude ainda** `FABRICA_PROVEDOR` e `FABRICA_PUBLICADOR` (continuam `falso`): salvar as chaves não gasta nada.
4. Confirme que o volume em **`/data`** continua anexado (sem ele, tudo some a cada deploy).

✔ **Pronto quando:** as variáveis estão salvas e o painel continua abrindo (modo simulação).

---

## Fase 4 — Primeiro vídeo REAL, sem publicar (barato)

Objetivo: ver a qualidade do vídeo e o custo real, **sem tocar no YouTube**.

1. Troque o conteúdo de **`FABRICA_CANAIS_JSON`** pelo do arquivo `canais.gta6-teste.json` (só o canal *GTA 6 Hoje*, **3 cenas**, começa 00:00). *(Se preferir, peça que eu faça: coloco a variável para você.)*
2. Mude **`FABRICA_PROVEDOR=real`** e deixe **`FABRICA_PUBLICADOR=falso`**. Salve (o servidor reinicia, ~1,5 min).
3. Abra o painel. Na aba **Escritório**, o agente do canal sai da fila e anda pelas estações: pesquisa → roteiro → narração → cenas → montagem → thumbnail (10–20 min).
4. Se o agente ficar com a **ampulheta** (pausado), é limite ou erro temporário: ele retoma sozinho. Veja o motivo nos *Logs* do Railway.
5. Quando aparecer um **1** na caixa de aprovação, abra **Painel → Aprovar** e **assista ao vídeo inteiro**. Confira:
   - os **fatos** (data, preço, plataforma, tudo o que for afirmado sobre GTA 6) contra fontes oficiais;
   - se **boato** foi dito como boato;
   - voz, ritmo, imagens (sem logo nem rosto oficial), thumbnails e títulos.
6. **Anote o gasto**: na aba *Caixa* (estimativa) e nos painéis da Anthropic e da OpenAI (real).
7. **Não aprove ainda.** Se algo não agradou, ajuste o `perfil` do canal (tom, estilo visual, evitar) e repita com outro tema.

✔ **Pronto quando:** você aprovaria o vídeo como está **e** o custo real ficou dentro do esperado.

---

## Fase 5 — Publicar UM vídeo de teste no YouTube

1. Mude **`FABRICA_PUBLICADOR=youtube`**. Salve.
2. No painel, aprove o vídeo da Fase 4 escolhendo título, thumbnail e **um horário daqui a ~20 minutos**.
3. Em poucos minutos o maestro envia. No **YouTube Studio** do canal, confira: o vídeo aparece como **Agendado** (privado com data), com a thumbnail escolhida, descrição, e o selo de **conteúdo alterado/sintético** marcado.
4. Espere o horário: ele deve ficar **público sozinho**. Se continuar privado, veja a nota de auditoria (2.4).
5. Apague o vídeo de teste no Studio se não quiser que fique no canal.

✔ **Pronto quando:** o vídeo foi enviado, agendou e publicou sozinho, com a thumbnail certa.

---

## Fase 6 — Ligar os canais aos poucos

**Cuidado:** ao ligar um canal cujo horário já passou, o maestro **produz na hora**. Ligue de manhã cedo, ou um de cada vez.

1. **Dia 1 — 1 canal:** volte as `cenas` do canal ao normal (10), com `FABRICA_CANAIS_JSON` só do *GTA 6 Hoje*. Aprove o vídeo do dia.
2. **Dia 2–3 — 3 canais:** *GTA 6 Hoje* + *Mitos e Verdades* + *Guia*. Veja se o YouTube aceita bem o conteúdo (sem avisos no Studio).
3. **Depois — os 6:** use o `canais.gta6.json` completo em `FABRICA_CANAIS_JSON`.
4. Conte os uploads: **6/dia** é o máximo com `shorts: 0` na cota padrão.
5. **Se o lançamento do jogo é agora**, comece pelos canais mais úteis na hora: *GTA 6 Hoje*, *Mitos e Verdades* e *Guia*.

⚠ **Risco de monetização:** vários canais gerados por IA sobre o mesmo assunto podem ser tratados como conteúdo repetitivo/em massa pelo YouTube. Os ângulos são diferentes de propósito, mas comece pequeno e acompanhe os avisos no Studio.

✔ **Pronto quando:** os canais ligados produzem e publicam por 2–3 dias sem erro, e o gasto diário é o que você esperava.

---

## Fase 7 — Rotina diária

**Todo dia (≈ 5 min):**
1. Abra o painel → **Aprovar**. Para cada vídeo: assista, confira fatos, escolha título/thumbnail e horário. **Aprovar é a única coisa obrigatória.**
2. Olhe o **Escritório**: ampulheta = pausado (retoma sozinho); vídeo **falhou** na lista *Fábrica* = precisa de você (veja *Logs*).
3. Olhe o **gasto do dia** no topo.

**Toda semana:** conferir os painéis de gasto (Anthropic, OpenAI), os avisos no YouTube Studio e se as vozes/imagens ainda estão boas.

**Limitações de hoje (saiba antes):**
- **Vídeo que falhou não é refeito sozinho** (ainda não existe botão "refazer").
- **As views ainda não viram moedas sozinhas** (falta ler as métricas do YouTube): o cofre só desce até você registrar views com `python -m fabrica views <id> <total>`.
- O painel **não recusa** vídeo: se não gostar, simplesmente não aprove.

**Segurança:**
- Depois de tudo funcionando, **apague o token da Vercel** em vercel.com/account/tokens.
- A chave do painel dá o poder de aprovar publicações: guarde como senha; para trocar, mude `FABRICA_PAINEL_CHAVE` no Railway.
- Se alguma chave vazar, gere outra no site da empresa e atualize no Railway.

---

## Checklist rápido

- [ ] Chave Claude + limite de gasto
- [ ] Chave OpenAI + limite de gasto (+ verificação da organização, se pedir)
- [ ] 6 canais criados e verificados no YouTube
- [ ] Projeto Google Cloud com API ativada e app **em produção**
- [ ] 6 tokens (um por canal, no canal certo)
- [ ] Railway com plano pago, variáveis salvas, volume em `/data`
- [ ] Vídeo de teste real (sem publicar) revisado e custo anotado
- [ ] Vídeo de teste publicado e agendado sozinho no YouTube
- [ ] Canais ligados aos poucos (1 → 3 → 6)
- [ ] Token da Vercel apagado
