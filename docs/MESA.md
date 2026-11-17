# Mesa de operações (Bitcoin e mercado financeiro) — simulação

> **Aviso.** Isto é um laboratório de pesquisa e **simulação**. Não é recomendação financeira, não garante lucro e **não envia ordens a nenhuma corretora**. Operar mercados envolve risco real de perda; a maioria das estratégias que parece boa no papel perde dinheiro quando enfrenta custos, atraso e dados novos.

## A ideia

Vários **agentes leitores** olham o mercado de jeitos diferentes e cada um devolve uma **probabilidade** de o preço estar mais alto daqui a N velas. Um **agregador** junta as leituras e mede se a probabilidade é **honesta** (calibrada). Um módulo de **risco** decide se opera, quanto e quando parar. Tudo passa por um **backtest** que não olha o futuro, desconta custos e diz com franqueza quando **não há evidência de vantagem**.

```
velas ──▶ leitores (tendência · momentum · reversão · fluxo/volume · notícias · regime[veto])
              │   cada um: probabilidade + confiança
              ▼
        agregador (média simples  ×  logística treinada walk-forward, probabilidades encolhidas)
              │   métricas: Brier, log-loss, tabela de calibração
              ▼
        risco: margem de probabilidade · valor esperado − custos > 0 · Kelly fracionado · stop ·
               limite de perda do dia · kill switch por drawdown · veto do regime
              ▼
        ordem SIMULADA, executada na abertura da vela seguinte (com taxa e derrapagem)
```

## Passo a passo no seu computador

**[docs/MESA_COMPUTADOR.md](MESA_COMPUTADOR.md)** — instalar o Python, baixar o histórico real, rodar o backtest, ler o resultado, o protocolo de teste e como decidir.

## Como usar (resumo)

```bash
# 1) dados reais do Bitcoin (sem chave; --fonte binance é a alternativa se a Coinbase estiver bloqueada na sua rede)
python -m mesa baixar --fonte coinbase --desde 2022-01-01 --saida btc.csv

# 2) backtest com custos, contra linhas de base (média simples e cada leitor sozinho)
python -m mesa backtest --dados btc.csv --horizonte 24 --json relatorio.json

# 3) o protocolo certo: ajuste SEM espiar o período final e teste UMA vez no que o modelo nunca viu
python -m mesa backtest --dados btc.csv --ate 2024-06-30      # onde você mexe e aprende
python -m mesa backtest --dados btc.csv --de   2024-07-01     # teste final: olhe uma vez só

# 4) ao vivo, SIMULADO: gera o sinal da última vela e guarda no diário; depois confere contra o que o preço fez
python -m mesa sinal   --dados btc.csv --diario diario.jsonl
python -m mesa avaliar --dados btc.csv --diario diario.jsonl
```

Sem dados reais à mão, `python -m mesa sintetico --modo ruido|momentum|regimes --saida x.csv` gera preços **inventados** para testar a estrutura. Eles **não são o mercado**.

## Leitores

| Leitor | O que olha |
|---|---|
| tendência | cruzamento de médias exponenciais, em unidades de volatilidade |
| momentum | retorno das últimas 24 velas |
| reversão à média | quão esticado o preço está em relação à média de 48 velas |
| fluxo e volume | pico de volume na direção da vela |
| regime de volatilidade | **veta** operações quando a volatilidade explode |
| **medo e ganância** (`--medo`) | índice diário (alternative.me, sem chave); contrário nos extremos; só conta 24 h depois de publicado |
| **funding** (`--funding binance\|bybit`) | taxa de financiamento dos perpétuos: muito positiva = compradores alavancados lotando um lado |
| notícias | interface pronta; falta um classificador de manchetes datadas |

Cada leitor só recebe o passado. Os de fora (medo e ganância, funding) guardam **quando cada dado foi publicado** e nunca devolvem nada do futuro (há teste automático).

## Varredura de horizontes (`mesa varrer`)

Roda o mesmo backtest em vários horizontes (padrão: 4, 8, 12, 24, 48 e 96 horas) e **corrige pelo número de testes**: com N testes, o limite de significância passa de 0,05 para 0,05 ÷ N (correção de Bonferroni). Só é "candidato" quem passa nessa correção, tem ≥ 30 operações e também é positivo no período de teste. Os horizontes devem ser escolhidos **antes** de olhar os resultados. O servidor roda a varredura sozinha (sobre o histórico já baixado) e a mostra na página de status; `MESA_VARREDURA=0` desliga.

## Backtest automático no servidor

O vigia, ao subir, **baixa sozinho 2 anos de histórico real** (Coinbase), roda o relatório (período completo + últimos 12 meses como teste, calibração, veredito) e mostra na página de status; **refaz toda semana**. Controles por variável de ambiente: `MESA_BACKTEST_DIAS` (padrão 730; `0` desliga), `MESA_MEDO` (`0` desliga o leitor de medo e ganância), `MESA_FUNDING` (`binance` ou `bybit`). Observação: servidores nos EUA (como o Railway em `iad`) costumam ser **bloqueados** pelas APIs de funding da Binance e da Bybit; nesse caso o relatório avisa e segue sem esse leitor.

## Monitorar 24 horas com dados reais (simulado)

```bash
python -m mesa vigiar --fonte coinbase --pasta dados-mesa      # fica rodando; Ctrl+C para parar
python -m mesa status --pasta dados-mesa                       # onde está: posição, resultado, último sinal
```

O **vigia** usa o preço **real** do Bitcoin (APIs públicas da Coinbase ou da Binance, **sem chave**) e faz tudo o que um robô faria, **só que com ordens de mentirinha**:

- **A cada 60 s** lê o preço, confere o **stop** e o **prazo** da posição simulada e atualiza o guarda de risco (limite do dia e kill switch).
- **A cada vela fechada** roda os agentes, grava o sinal no diário e, se o risco permitir, **abre uma posição simulada**.
- Guarda tudo em disco (`velas.csv`, `diario.jsonl`, `estado.json`, `eventos.log`): se reiniciar, **continua de onde parou**. Erro de rede não derruba; ele tenta de novo.

Fonte de dados: use `--fonte coinbase` se rodar num servidor nos EUA (como o Railway em `iad`): a Binance global **bloqueia IPs dos EUA**. No seu computador no Brasil, a Binance costuma funcionar.

**No Railway, sem pagar outro serviço:** o mesmo serviço pode rodar a mesa no lugar da fábrica de vídeos. Basta definir a variável **`FABRICA_MODO=mesa`** (opcional: `MESA_FONTE=coinbase|binance`, `MESA_PASTA=/data/mesa`). O vigia sobe junto com uma **página de status** protegida pela chave do painel (`https://SEU-ENDERECO/?k=CHAVE`) e o `/saude` usado pelo Railway. Para **voltar à fábrica de vídeos**, apague `FABRICA_MODO`. Os dados da mesa ficam em `/data/mesa`, separados dos da fábrica.

Quer rodar os dois ao mesmo tempo? Aí são dois serviços (dois processos), com custo próprio no seu plano.

Isso já gera o que mais importa: **resultado ao vivo, com preço real, sem risco**, para comparar com o backtest depois de semanas.

## Como ler o resultado

- **IC 95% por operação**: o intervalo (por *bootstrap*) do retorno médio por operação. "Evidência de vantagem" só aparece com **≥ 30 operações** e o intervalo **inteiro acima de zero**. É evidência, **não prova**.
- **Brier / log-loss**: chutar 50% dá Brier 0,2500 e log-loss 0,6931. Se o agregador não fica abaixo disso **fora da amostra**, ele não sabe nada.
- **Tabela de calibração**: quando diz 70%, tem de subir ~70% das vezes. Se não, a probabilidade é enganosa.
- Sempre compare com **buy & hold** e com as **linhas de base**: se a média simples ou um único leitor faz o mesmo, a complexidade não se paga.

## O que já foi verificado (com preços inventados)

- Em **ruído puro** (sem vantagem nenhuma), o sistema **não encontra vantagem** em nenhuma das sementes testadas.
- Com uma **vantagem real, mas pequena**, ele a detecta quando os custos são baixos — e **a vantagem desaparece com custos realistas** (taxa 0,10% + derrapagem 0,05% por lado). Isso é o comportamento esperado e honesto.
- As leituras **não mudam** quando o futuro é alterado (teste automático), o treino só usa amostras cujo resultado já era conhecido, e o stop, o limite do dia e o kill switch estão cobertos por testes.

Isto valida a **estrutura**. **Não** diz nada sobre se existe vantagem no Bitcoin real: isso só os dados reais e o paper trading respondem.

## Armadilhas que o sistema tenta evitar (e você também deve)

1. **Olhar o futuro** (lookahead): cada leitor só recebe o passado; a ordem entra na vela seguinte.
2. **Ajustar até dar certo**: por isso o protocolo `--ate` / `--de`. Cada vez que você olha o período de teste e muda algo, ele deixa de ser teste.
3. **Custos esquecidos**: taxa e derrapagem entram nos dois lados.
4. **Muitos testes, uma vitória por sorte**: testar 20 variações e ficar com a melhor quase sempre acha "vantagem" no ruído.
5. **Dado ruim**: o carregador recusa tempo repetido e preço impossível.

## O que falta (por ordem)

1. **Dados reais** e a primeira rodada do protocolo acima.
2. **Mais leitores**: derivativos de cripto (funding, open interest), livro de ofertas, e o leitor de **notícias** com um classificador de manchetes datadas (a interface já existe e já não enxerga o futuro).
3. **Paper trading contínuo**: o comando `sinal` periódico (como o maestro da fábrica), com painel.
4. **Execução em corretora** — **não existe no código**, de propósito. Só depois de semanas/meses de paper trading que **vençam uma estratégia simples depois de custos**, e nesta ordem:
   1. **Testnet** da corretora (dinheiro de mentirinha, API de verdade): serve para testar o envio, o tratamento de erros e ordens que falham.
   2. **Chave de API só com permissão de operar**, **nunca de saque**, restrita ao IP do servidor.
   3. **Capital pequeno**, que você aceita perder por inteiro, com os mesmos limites do risco no código (perda do dia, kill switch).
   4. **Aprovação humana por ordem** no começo (como na fábrica de vídeos), e só depois automático.
   5. Regras do país: operar o próprio dinheiro é uma coisa; operar o de terceiros exige autorização.
