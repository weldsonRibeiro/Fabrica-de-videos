# Rodar a mesa no seu computador — passo a passo

> **Aviso.** Tudo aqui é **simulação**. Nada envia ordens a corretoras e você não precisa de conta, chave ou dinheiro. Não é recomendação financeira; o objetivo é descobrir **com honestidade** se existe alguma vantagem nos dados reais do Bitcoin — e a resposta mais provável, depois de custos, é "não".

Tempo total: cerca de 20 minutos. Funciona em Windows, macOS e Linux.

---

## Passo 1 — Instalar o Python (3.10 ou mais novo)

- **Windows:** baixe em **python.org/downloads**, abra o instalador e **marque "Add python.exe to PATH"** antes de clicar em *Install*.
- **macOS:** `brew install python` (ou o instalador do python.org).
- **Linux:** `sudo apt install python3` (já vem na maioria).

Confira abrindo o terminal (Windows: *PowerShell*; Mac/Linux: *Terminal*):
```bash
python --version        # Windows pode ser: py --version   |   Mac/Linux pode ser: python3 --version
```
Tem que mostrar `3.10` ou maior. **Nos comandos abaixo, use `py` (Windows) ou `python3` (Mac/Linux) se `python` não funcionar.**

## Passo 2 — Baixar o código

**Com Git:**
```bash
git clone https://github.com/weldsonRibeiro/Fabrica-de-videos
cd Fabrica-de-videos
```
**Sem Git:** abra o repositório no GitHub → botão verde **Code → Download ZIP**, extraia e entre na pasta pelo terminal (`cd` até ela).

Não há nada para instalar: o módulo da mesa usa só a biblioteca padrão do Python.

Confira que está tudo certo:
```bash
python -m mesa --help
```

## Passo 3 — Baixar o histórico REAL do Bitcoin

```bash
python -m mesa baixar --fonte coinbase --desde 2022-01-01 --saida btc.csv
```
- Demora de 1 a 3 minutos (mostra `N velas…` enquanto baixa). Não precisa de chave.
- No fim aparece quantas velas vieram e **quantas faltavam no meio** (buracos no histórico; o programa os trata).
- Se der erro de rede/região, tente a outra fonte: `--fonte binance`.

## Passo 4 — Primeiro backtest

```bash
python -m mesa backtest --dados btc.csv --meses-teste 12 --json relatorio.json
```
Leva de 1 a 3 minutos. Ele imprime:

1. **PERÍODO COMPLETO** e **TESTE: últimos 12 meses** — uma linha por estratégia: o sistema completo (**agentes + logístico**), a **média simples**, e **cada leitor sozinho**. Colunas: retorno, **buy & hold** (comprar e segurar), Sharpe, queda máxima, nº de operações, intervalo de confiança do retorno por operação e o veredito.
2. **Calibração**: o **Brier** (chutar 50% dá 0,2500; abaixo disso as probabilidades têm algum valor) e se, quando ele diz 60%, o preço sobe ~60% das vezes.
3. **VEREDITO** em português.

### Como ler (o que realmente importa)
| Olhe isto | Bom sinal | Mau sinal |
|---|---|---|
| **Veredito** | "evidência de vantagem" **também no teste dos últimos 12 meses** | "SEM evidência" |
| **Retorno × buy & hold** | ganha do buy & hold **com queda máxima menor** | rende menos que só comprar e segurar |
| **Brier / calibração** | Brier < 0,2500 e a tabela "diz X% → subiu X%" bate | Brier ≥ 0,2500, probabilidades que não se confirmam |
| **Operações** | ≥ 30 (senão não dá para concluir nada) | poucas operações |
| **Uma estratégia só "com evidência"** entre várias | desconfie: 1 em 20 aparece por sorte | — |

## Passo 5 — Testar sem se enganar (o protocolo)

O teste dos últimos 12 meses só vale enquanto você **não ajusta nada olhando para ele**. Regra de ouro:
```bash
python -m mesa backtest --dados btc.csv --ate 2024-12-31      # aqui você mexe, compara, aprende
python -m mesa backtest --dados btc.csv --de  2025-01-01      # teste final: olhe UMA vez e pare
```
Cada vez que você muda algo depois de ver o teste final, ele deixa de ser teste. **Anote cada variação que tentar**: quanto mais variações, menos confiável fica a "melhor".

## Passo 6 — Leitores extras (opcional)

```bash
python -m mesa backtest --dados btc.csv --medo                      # índice de medo e ganância (sem chave)
python -m mesa backtest --dados btc.csv --funding bybit            # funding dos perpétuos (ou: --funding binance)
python -m mesa backtest --dados btc.csv --medo --funding bybit
```
Se uma API estiver bloqueada na sua rede, o relatório avisa ("indisponível") e segue sem ela. Compare: o leitor novo **melhorou** o Brier e o veredito, ou só mudou o número?

## Passo 7 — Experimentar parâmetros (com cuidado)

```bash
python -m mesa backtest --dados btc.csv --horizonte 12          # cada operação dura 12 horas (padrão: 24)
python -m mesa backtest --dados btc.csv --taxa 5 --slippage 2   # custos menores (só se for a sua realidade)
python -m mesa backtest --dados btc.csv --short                 # permite vender a descoberto (derivativos)
```
Custos são decisivos: **teste sempre com os custos reais da sua corretora**. Vantagens pequenas costumam sumir com 0,10% de taxa + 0,05% de derrapagem por lado.

### Varredura de horizontes (com a correção certa)

Em vez de testar horizontes um a um (e ficar com o que "deu certo"), rode todos de uma vez, **com a lista definida antes de olhar o resultado**:
```bash
python -m mesa varrer --dados btc.csv --horizontes 4,8,12,24,48,96 --json varredura.json
```
O resultado corrige pelo **número de testes feitos** (horizontes × estratégias): o limite de significância é dividido por esse número. Um candidato só "sobrevive" se passar nessa correção **e** for positivo também nos últimos 12 meses. O veredito diz quantos positivos você esperaria só por sorte. Mesmo quem sobrevive é uma **hipótese**: a confirmação limpa é o paper trading ao vivo. O servidor já roda essa varredura sozinho e mostra na página de status.

## Passo 8 — Ao vivo, simulado, no seu computador (opcional)

O **servidor do Railway já faz isso 24 h** (veja o Passo 10). Rodar também no computador só duplica o resultado, mas serve para entender o funcionamento:
```bash
python -m mesa vigiar --pasta dados-mesa            # deixe o terminal aberto; Ctrl+C para parar
python -m mesa status --pasta dados-mesa            # em outro terminal: posição, resultado, último sinal
```
Quer só uma checagem por hora, sem deixar nada aberto? Use `python -m mesa vigiar --pasta dados-mesa --uma-vez` no **Agendador de Tarefas** (Windows) ou no **cron** (Mac/Linux), de hora em hora.

## Passo 8b — Hipótese H1 (funding): o teste pré-registrado

Este é o **único teste novo planejado** (veja `docs/RESULTADOS.md`). O protocolo está **travado no código**: horizonte de 24 h, custo de 0,15% por lado, 2 testes e os critérios de aprovação. **Não existem parâmetros para mexer** — de propósito.

```bash
python -m mesa baixar --fonte coinbase --desde 2024-11-01 --saida btc.csv       # precisa de ≥ 8.000 velas de 1 h (≈ 11 meses)
python -m mesa hipotese funding --dados btc.csv --funding bybit --json h1.json   # ou: --funding binance
```
- Baixa o funding sozinho (se a API estiver bloqueada na sua rede, tente a outra: `--funding binance` ou `bybit`).
- Imprime o protocolo, os resultados e cada critério com ✓ ou ✗, e o **veredito**.
- **REPROVADA** → a hipótese está encerrada. **Não** mude nada e rode de novo; para testar outra ideia, ela precisa ser escrita antes.
- **APROVADA** → vira candidata a **paper trading ao vivo** (≥ 8 semanas, ≥ 30 operações). **Não** é luz verde para dinheiro real. Me avise e eu preparo o vigia com o leitor de funding (no servidor ele não funciona, as APIs bloqueiam IPs dos EUA).

## Passo 8c — Curto prazo na Binance: coletar 24 h e medir o custo de equilíbrio (H2)

Objetivo: ganhar na **quantidade** de operações. A conta que decide tudo: **ganho bruto médio por operação** tem de ser **maior** que o custo de entrar e sair (2 × taxa por lado). Em vez de apostar, medimos.

Tudo aqui é **simulação e leitura de dados públicos**: nenhuma chave da Binance é pedida e nenhuma ordem é enviada.

**1) Descubra a SUA taxa** (app/site da Binance → perfil → *Nível de taxas*): normalmente 0,10% por lado no spot, 0,075% pagando com BNB. Alguns pares têm taxa zero em promoções. Quanto menor, melhor para o teste.

**2) Baixe ~3 meses de velas de 1 minuto** (≈ 130 mil velas; leva alguns minutos):
```powershell
python -m mesa baixar --fonte binance --intervalo 1m --desde 2026-08-15 --saida btc1m.csv
```

**3) Rode o teste H2** (protocolo fixo no código: horizontes de 5, 15, 30 e 60 min × 2 agregadores = 8 testes, correção de Bonferroni):
```powershell
python -m mesa curto --dados btc1m.csv --json h2.json
```
O padrão é 0,10% por lado (10 bps), a taxa de uma conta nova sem BNB. Se a sua for diferente, acrescente `--taxa-bps 7.5` (0,075% com BNB) ou o valor do seu *Nível de taxas*. A taxa é um fato da sua conta, por isso fica registrada no resultado.

Como ler:
- **PARTE 1** mostra, sem custo nenhum, quantas operações por dia os agentes fariam e o **ganho bruto por operação** em bps (1 bp = 0,01%). O **equilíbrio** é a maior taxa por lado com que ainda se empata. Se for **menor** que a sua taxa (+1 bp de derrapagem), a estratégia perde dinheiro — por mais operações que faça, só multiplica a perda.
- **PARTE 2** roda com o seu custo e aplica os critérios: ≥ 200 operações, p ≤ 0,00625 e retorno positivo no período inteiro e nas duas metades.
- **REPROVADA** → hipótese encerrada, sem ajustar números. **APROVADA** → vira candidata a paper trading ao vivo (≥ 8 semanas, ≥ 200 operações), **não** a dinheiro real.

**4) Coletor 24 h** (deixe o computador ligado; Ctrl+C para parar). Guarda velas de 1 min e a foto do melhor preço de compra/venda a cada 10 s — com isso medimos o **spread real**, que é um custo oculto:
```powershell
python -m mesa coletar --fonte binance --pasta dados-curto
python -m mesa coletar --pasta dados-curto --resumo      # em outro terminal: dias coletados e spread médio/p95
```
Os arquivos (`velas1m.csv`, `livro.csv`) ficam na pasta e podem ser usados no passo 3 (`--dados dados-curto/velas1m.csv`) quando tiver dias suficientes.

**5) Agentes ao vivo em 1–5 minutos (simulado)**, para ver as probabilidades chegando:
```powershell
python -m mesa vigiar --fonte binance --intervalo 1m --horizonte 15 --checagem 15 --taxa 10 --slippage 1 --pasta dados-mesa-1m
```
Se, no passo 3, a estratégia for reprovada, esse modo ao vivo só vai confirmar em tempo real o que o teste já mostrou: tudo bloqueado por "valor esperado não cobre os custos".

## Passo 9 — Atualizar o código quando eu avisar

```bash
git pull
```
(Sem Git: baixe o ZIP de novo.)

## Passo 10 — Comparar com o servidor

Abra a página de status do servidor (`https://fabricade-videos.vercel.app/?k=SUA_CHAVE`): ela mostra o **backtest que o próprio servidor roda sozinho** (2 anos de histórico, refeito toda semana), a posição simulada e o que cada agente pensa agora. Os números devem ser parecidos com os do seu computador para o mesmo período e as mesmas configurações — se não forem, algo está diferente (período, custos, leitores).

## Passo 11 — Decidir o que fazer com o resultado

| Resultado | O que fazer |
|---|---|
| **"SEM evidência"** no completo ou no teste | **Pare por aqui.** Não há base para dinheiro real. Pode tentar novos leitores/ideias, mas sem ajustar olhando o teste final. |
| Evidência no completo mas **não** no teste dos últimos 12 meses | Provável sorte ou um regime que acabou. **Não avance.** |
| Evidência **nos dois**, Brier < 0,2500, ganha do buy & hold com risco menor | Siga para **paper trading ao vivo por 4 a 8 semanas** (o servidor já está fazendo) e compare o resultado ao vivo com o do backtest. |
| Paper trading ao vivo confirma | Só então pense em **testnet** da corretora (dinheiro de mentirinha, API de verdade). Dinheiro real fica para depois e **só capital que você aceita perder inteiro**. |

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `python` não é reconhecido | Use `py` (Windows) ou `python3` (Mac/Linux); no Windows, reinstale marcando *Add to PATH*. |
| `CERTIFICATE_VERIFY_FAILED` (Mac) | Na pasta *Aplicativos/Python 3.x*, rode **Install Certificates.command**. |
| `não consegui baixar … HTTP 403/451` | A região/rede bloqueia essa fonte: troque `--fonte coinbase` por `--fonte binance` (ou o contrário). |
| `poucas velas depois do filtro de período` | Baixe mais histórico (`--desde` mais antigo) ou use um período maior. São necessárias ~700 velas no mínimo. |
| Demora muito | 3 anos de velas de 1 h levam 1–3 min; mais que isso, feche outros programas. |
| `funding … indisponível` | Essa API está bloqueada na sua rede: use `--funding binance` ou `bybit`, ou siga sem ele. |
