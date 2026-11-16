"""Página de status da mesa (somente leitura): preço, resultado simulado, posição, o que cada agente pensa e os eventos.

Lê os arquivos que o vigia grava (estado.json, eventos.log). Protegida pela chave FABRICA_PAINEL_CHAVE (mesmo esquema do
painel da fábrica: `/?k=CHAVE` vira cookie). `/saude` é público e só responde {"ok": true}.
"""
from __future__ import annotations

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

COOKIE = "mesa_chave"

PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0e1116"><title>Mesa — Bitcoin (simulação)</title>
<style>
:root{--bg:#0e1116;--card:#171b22;--linha:#2a313c;--txt:#eef1f5;--suave:#9aa5b4;--ok:#4cc9a0;--neg:#ff8a7a;--aviso:#f0a94a;--marca:#6b93ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:720px;margin:0 auto;padding:max(14px,env(safe-area-inset-top)) 16px 48px}
h1{font-size:1.15rem;margin:0}h2{font-size:.8rem;color:var(--suave);text-transform:uppercase;letter-spacing:.05em;margin:24px 0 8px}
.topo{display:flex;justify-content:space-between;align-items:center;gap:10px}
.selo{font-size:.72rem;font-weight:800;border:1px solid var(--aviso);color:var(--aviso);padding:3px 10px;border-radius:999px;white-space:nowrap}
.card{background:var(--card);border:1px solid var(--linha);border-radius:14px;padding:14px}
.preco{font-size:2rem;font-weight:800;font-variant-numeric:tabular-nums}.grande{font-size:1.4rem;font-weight:800}
.pos{color:var(--ok)}.neg{color:var(--neg)}.suave{color:var(--suave);font-size:.85rem}
.grade{display:grid;grid-template-columns:1fr 1fr;gap:10px}.grade .card{padding:12px}
.barra{height:10px;border-radius:5px;background:var(--linha);position:relative;margin:10px 0 4px}
.barra i{position:absolute;top:-3px;width:4px;height:16px;border-radius:2px;background:var(--marca)}
.barra b{position:absolute;left:50%;top:0;width:1px;height:10px;background:var(--suave)}
.linha{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid var(--linha);font-size:.92rem}.linha:last-child{border:0}
.log{font:.78rem/1.5 ui-monospace,Menlo,monospace;color:var(--suave);white-space:pre-wrap;overflow-wrap:anywhere}
.aviso{margin-top:22px;color:var(--suave);font-size:.78rem}
</style></head><body><main>
<div class="topo"><h1>₿ Mesa · Bitcoin</h1><span class="selo">SIMULAÇÃO</span></div>
<div class="card" style="margin-top:12px"><div class="suave">preço</div><div class="preco" id="preco">—</div><div class="suave" id="atualizado"></div></div>
<h2>Resultado simulado</h2>
<div class="grade"><div class="card"><div class="suave">capital</div><div class="grande" id="equity">—</div></div>
<div class="card"><div class="suave">resultado</div><div class="grande" id="res">—</div></div></div>
<h2>Posição e risco</h2><div class="card"><div id="pos">—</div><div class="suave" id="risco" style="margin-top:6px"></div></div>
<h2>O que os agentes pensam agora</h2><div class="card"><div class="suave" id="sinal">—</div>
<div class="barra"><b></b><i id="marcador" style="left:50%"></i></div><div class="suave" style="display:flex;justify-content:space-between"><span>queda</span><span id="pa"></span><span>alta</span></div>
<div id="leituras" style="margin-top:8px"></div></div>
<h2>Operações simuladas</h2><div class="card" id="trades"></div>
<h2>Eventos</h2><div class="card log" id="eventos"></div>
<p class="aviso">⚠️ Simulação com preço real. Nenhuma ordem real é enviada. Passado não garante futuro; não é recomendação financeira.</p>
</main><script>
const $=id=>document.getElementById(id),f=(n,d=2)=>n.toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d}),el=(t,c,x)=>{const n=document.createElement(t);if(c)n.className=c;if(x!==undefined)n.textContent=x;return n};
async function atualizar(){
  let r;try{r=await fetch("/api/estado",{credentials:"same-origin"});}catch(e){return}
  if(r.status===401){document.body.textContent="Acesso negado. Abra o link com a chave (?k=...).";return}
  const d=await r.json();if(!d.estado){$("preco").textContent="aguardando o primeiro ciclo…";return}
  const e=d.estado,c=e.corretora,res=e.equity/c.capital_inicial-1;
  $("preco").textContent="US$ "+f(e.preco);$("atualizado").textContent="atualizado "+e.atualizado_em.replace("T"," ").slice(0,19)+" UTC";
  $("equity").textContent=f(e.equity);const rs=$("res");rs.textContent=(res>=0?"+":"")+f(res*100)+"%";rs.className="grande "+(res>=0?"pos":"neg");
  const p=c.posicao;$("pos").textContent=p?(p.direcao>0?"COMPRADO":"VENDIDO")+" "+f(p.fracao*100,1)+"% do capital · entrada "+f(p.entrada)+" · stop "+f(p.stop):"fora do mercado";
  $("risco").textContent=e.guarda.desligado?"⛔ DESLIGADO: "+e.guarda.motivo:"risco: ok · pico "+f(e.guarda.pico);
  const s=e.ultimo_sinal;$("leituras").replaceChildren();
  if(s){$("sinal").textContent=s.motivo+(s.p!=null?"":"");if(s.p!=null){$("marcador").style.left=(s.p*100)+"%";$("pa").textContent="p(alta) "+f(s.p*100,0)+"%"}
    for(const l of s.leituras){const x=el("div","linha");x.append(el("span","",l.leitor),el("span","suave","p "+f(l.p*100,0)+"% · conf. "+f(l.conf,2)+" · "+l.nota));$("leituras").append(x)}}
  const t=$("trades");t.replaceChildren();const ts=c.trades.slice(-8).reverse();
  if(!ts.length)t.append(el("div","suave","nenhuma operação fechada ainda"));
  for(const x of ts){const l=el("div","linha");l.append(el("span","",(x.direcao>0?"compra":"venda")+" · "+x.motivo),el("span",x.ret_capital>=0?"pos":"neg",(x.ret_capital>=0?"+":"")+f(x.ret_capital*100)+"%"));t.append(l)}
  $("eventos").textContent=d.eventos.join("\\n")||"—";
}
atualizar();setInterval(atualizar,10000);
</script></body></html>"""


def _estado(pasta: Path) -> dict:
    arq = pasta / "estado.json"
    eventos = []
    log = pasta / "eventos.log"
    if log.exists():
        eventos = log.read_text(encoding="utf-8").splitlines()[-15:]
    return {"estado": json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None, "eventos": eventos}


def servidor(pasta: Path | str, chave: str, host: str = "127.0.0.1", porta: int = 8080) -> ThreadingHTTPServer:
    if len(chave) < 16:
        raise ValueError("a chave do painel precisa ter pelo menos 16 caracteres (FABRICA_PAINEL_CHAVE)")
    pasta = Path(pasta)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _autorizado(self) -> bool:
            for parte in self.headers.get("Cookie", "").split(";"):
                nome, _, valor = parte.strip().partition("=")
                if nome == COOKIE and hmac.compare_digest(valor, chave):
                    return True
            return False

        def _resp(self, status, corpo: bytes, tipo, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/saude":
                return self._resp(200, b'{"ok": true}', "application/json")
            k = parse_qs(url.query).get("k", [""])[0]
            if url.path == "/" and k:
                if not hmac.compare_digest(k, chave):
                    return self._resp(401, b'{"erro": "chave invalida"}', "application/json")
                seguro = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                return self._resp(303, b"", "text/plain", {"Location": "/", "Set-Cookie": f"{COOKIE}={chave}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000{seguro}"})
            if not self._autorizado():
                return self._resp(401, "Acesso restrito: abra o link completo, com ?k=SUA_CHAVE no final.".encode(), "text/plain; charset=utf-8")
            if url.path == "/":
                return self._resp(200, PAGINA.encode(), "text/html; charset=utf-8")
            if url.path == "/api/estado":
                return self._resp(200, json.dumps(_estado(pasta), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            self._resp(404, b'{"erro": "nao encontrado"}', "application/json")

    return ThreadingHTTPServer((host, porta), Handler)


def servir_em_segundo_plano(pasta, chave, host, porta) -> ThreadingHTTPServer:
    srv = servidor(pasta, chave, host, porta)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
