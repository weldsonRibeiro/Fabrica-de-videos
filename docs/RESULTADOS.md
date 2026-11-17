# Caderno de pesquisa — Bitcoin (simulação)

> Registro honesto do que foi testado e do que apareceu. Só simulação: nada aqui envia ordens a corretoras, e nada é recomendação financeira.

## Conclusão (17/11/2026)

**Com indicadores de preço e volume públicos, no Bitcoin de 1 hora, não há evidência de vantagem.** Em 42 testes (6 horizontes × 7 estratégias) com os custos reais de uma corretora comum, **nenhum** sobreviveu à correção pelo número de testes. As probabilidades dos agentes não são melhores que chutar 50%. Os resultados negativos vêm dos custos: a vantagem bruta é praticamente zero.

## O que foi testado

| | |
|---|---|
| Dados | Coinbase BTC-USD, velas de 1 h, 17.520 velas (17/11/2024 → 16/11/2026); 10 velas faltantes foram repetidas do fechamento anterior |
| Custos | taxa de 0,10% + derrapagem de 0,05% por lado (0,30% de ida e volta) |
| Leitores | tendência, momentum, reversão à média, fluxo e volume, regime de volatilidade (veto), medo e ganância |
| Agregadores | média simples e regressão logística treinada em janela móvel (só com resultados já conhecidos), com probabilidades encolhidas |
| Risco | Kelly fracionado (½), teto de 50% do capital, perda máxima de 1% por operação (stop), limite de perda de 3% no dia, kill switch em −20% |
| Teste | últimos 12 meses (desde 21/11/2025); o código **não** foi ajustado olhando esses dados |

## Resultados

**Horizonte de 24 h, período completo** (comprar e segurar: −33,9%):

| Estratégia | Retorno | Operações | IC 95% por operação |
|---|---|---|---|
| agentes + logística | −6,0% | 99 | [−0,12% ; +0,00%] |
| agentes + média simples | −1,3% | 31 | [−0,11% ; +0,03%] |
| só tendência | −0,7% | 22 | poucas operações |
| só momentum | −11,6% | 232 | [−0,09% ; −0,01%] |
| só reversão à média | −20,2% (kill switch) | 215 | [−0,17% ; −0,04%] |
| só fluxo e volume | −14,7% | 245 | [−0,10% ; −0,03%] |
| só medo e ganância | +0,9% | 16 | poucas operações |

**Últimos 12 meses** (comprar e segurar: −23,8%): logística −1,8% (12 ops), média simples −0,7% (20), tendência +0,3% (10), reversão −3,7% (33), momentum −7,1% (109), fluxo −5,3% (110), medo e ganância +0,4% (13).

**Calibração das probabilidades (24 h, 16.853 previsões fora da amostra):** Brier 0,2537 (chutar 50% = 0,2500), log-loss 0,7007 (50% = 0,6931), acerto de 48,1%. Quando o agregador dizia 60–70%, o preço subiu 42% das vezes.

**Varredura de horizontes (4, 8, 12, 24, 48 e 96 h):** 42 testes; limite corrigido (Bonferroni) p ≤ 0,0012; por sorte esperariam-se ~2,1 positivos, apareceram **0**. Retorno de agentes + logística / média simples entre −6,0% e ≈ 0 em todos os horizontes; nenhum intervalo de confiança inteiro acima de zero; Brier entre 0,2498 e 0,2559; acerto entre 48,1% e 51,4%. No horizonte de 4 h o sistema quase não opera (0 a 13 operações), porque os 0,30% de custo comem o valor esperado.

## Como interpretar

- Os leitores não têm vantagem bruta; os custos transformam esse zero em prejuízo. Momentum e fluxo/volume têm retorno líquido por operação significativamente **negativo**, não porque "funcionem ao contrário", mas porque pagam custo sem ganhar nada.
- Perder menos que "comprar e segurar" (−33,9%) **não é mérito**: as estratégias ficam a maior parte do tempo fora do mercado, num período em que o Bitcoin caiu.
- **Medo e ganância** (+0,9% e +0,4%) pode parecer promissor, mas com 13 a 16 operações não permite concluir nada.
- O período de teste de 12 meses já havia sido visto com o horizonte de 24 h antes da varredura; por isso a varredura conta como **exploração**.

## Limites (o que este resultado NÃO diz)

- Não diz que **nenhuma** estratégia funciona no Bitcoin; diz que **estas**, com **estes** dados públicos e **estes** custos, não mostraram vantagem.
- O leitor de **funding** não foi testado (as APIs bloqueiam o servidor, que fica nos EUA). É a hipótese H1 abaixo.
- Dois anos de um único ativo e um único regime de mercado. Custos menores (ex.: ordens limitadas, taxas de maker) poderiam mudar o resultado líquido, **mas a vantagem bruta estimada é ≈ zero**, e custo menor sozinho não cria vantagem.

## Próximos passos (definidos ANTES de ver qualquer resultado)

### 1. Paper trading ao vivo (já rodando no servidor)
É o único teste limpo: dados que não existiam quando o sistema foi escrito. **Critério fixado:** só reavaliar com **≥ 8 semanas E ≥ 30 operações simuladas**; aprova somente se o retorno líquido for positivo **e** o IC 95% por operação ficar acima de zero. Antes disso, qualquer resultado é ruído. O placar aparece na página de status.

### 2. Hipótese H1 — funding (no seu computador)
> *O funding dos perpétuos (compradores alavancados lotando um lado) carrega informação sobre o retorno das próximas 24 h que os indicadores de preço não têm.*

Protocolo **travado no código** (`mesa/hipotese.py`; a linha de comando **não tem parâmetros** para mexer): horizonte 24 h, custo de 0,15% por lado, 2 testes ("só funding" e "agentes + funding"), limite p ≤ 0,025. **Aprova** só se: ≥ 30 operações; p ≤ 0,025; retorno líquido > 0 no período inteiro **e em cada metade**; e (para agentes + funding) Brier < 0,25 e melhor que o dos mesmos agentes sem funding.

- **Reprovou:** a hipótese está encerrada. Não ajustar e repetir.
- **Aprovou:** vira candidata a **paper trading ao vivo** (≥ 8 semanas), **nunca** direto a dinheiro real.

Como rodar: `docs/MESA_COMPUTADOR.md`, "Hipótese H1".

### 3. Encerramento
Se H1 reprovar **e** o paper trading não confirmar nada em 8 semanas, **encerra-se a pesquisa de sinais no Bitcoin com indicadores públicos**. É um resultado útil: evita perder dinheiro com uma ilusão.

## Regras para não se enganar (valem daqui para frente)

1. Nova ideia = nova hipótese **escrita antes** de rodar, com critério de aprovação fixo.
2. Quantos testes foram feitos? Sempre corrigir por esse número.
3. Mexeu em algo depois de ver o resultado? Aquele período deixou de ser teste.
4. Só o paper trading ao vivo confirma. Backtest bonito é hipótese.
5. Dinheiro real só depois de tudo isso, com capital que se aceita perder inteiro, testnet primeiro e aprovação humana por ordem.
