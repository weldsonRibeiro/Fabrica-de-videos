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

## Como usar

```bash
# 1) dados reais do Bitcoin (rode no SEU computador; a Binance pública não pede chave, mas algumas redes a bloqueiam)
python -m mesa baixar --simbolo BTCUSDT --intervalo 1h --desde 2021-01-01 --saida btc.csv

# 2) backtest com custos, contra linhas de base (média simples e cada leitor sozinho)
python -m mesa backtest --dados btc.csv --horizonte 24

# 3) o protocolo certo: ajuste SEM espiar o período final e teste UMA vez no que o modelo nunca viu
python -m mesa backtest --dados btc.csv --ate 2024-06-30      # onde você mexe e aprende
python -m mesa backtest --dados btc.csv --de   2024-07-01     # teste final: olhe uma vez só

# 4) ao vivo, SIMULADO: gera o sinal da última vela e guarda no diário; depois confere contra o que o preço fez
python -m mesa sinal   --dados btc.csv --diario diario.jsonl
python -m mesa avaliar --dados btc.csv --diario diario.jsonl
```

Sem dados reais à mão, `python -m mesa sintetico --modo ruido|momentum|regimes --saida x.csv` gera preços **inventados** para testar a estrutura. Eles **não são o mercado**.

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
