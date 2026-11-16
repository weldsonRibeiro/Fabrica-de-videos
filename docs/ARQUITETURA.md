# Arquitetura

```
            ┌────────────────────────── Maestro (tick a cada minuto) ──────────────────────────┐
            │  1. garante a agenda de hoje (e de amanhã, a partir das 20h)                       │
            │  2. produz vídeos AGENDADOS cuja hora chegou e PAUSADOS cujo retomar_em chegou     │
            │  3. publica vídeos APROVADOS                                                       │
            │  4. lança despesas na carteira                                                     │
            └───────────────┬─────────────────────────────────────────────┬──────────────────────┘
                            │                                             │
                     Pipeline (agente da sala)                      Publicador
   pesquisa → roteiro → narração → cenas → montagem → thumbnail      (YouTube...)
        │  checkpoint após cada etapa; LimiteAtingido → PAUSADO
        ▼
   AGUARDANDO_APROVAÇÃO ──(dono escolhe título, thumb, horário)──▶ APROVADO ──▶ AGENDADO_NO_CANAL
```

## Máquina de estados do vídeo

`agendado → em_producao → aguardando_aprovacao → aprovado → agendado_no_canal`

- `em_producao → pausado → em_producao` quando a IA trava ou bate no limite.
- `em_producao → falhou` após esgotar as tentativas de uma etapa.

## Decisões

- **Estado em JSON, um arquivo por vídeo, escrita atômica.** Simples de inspecionar e suficiente
  para a fase de validação. Troca por SQLite/Postgres quando houver painel e múltiplos workers.
- **`tick` idempotente.** Pode ser chamado por cron a cada minuto, ou duas vezes seguidas, sem
  duplicar vídeos nem cobranças.
- **Provedores por contrato (`Provedor`, `Publicador`).** Cada etapa pode ter um provedor diferente;
  o falso permite testar a fábrica sem gastar nada.
- **Despesa e moeda idempotentes.** A carteira guarda o que já lançou por vídeo e só aplica a diferença.

## Pontos em aberto

- Qual hospedagem do worker (Railway, Cloudflare, VPS)? O `tick` precisa rodar de forma contínua.
- Armazenamento dos arquivos gerados (R2/S3) em vez de caminhos locais.
- Fuso horário: hoje a agenda usa o horário local do servidor; definir fuso por canal.
- Como o jogo mostra o "escritório" (2D? só um painel?) — ver `docs/JOGO.md`.
