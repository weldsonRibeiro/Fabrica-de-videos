/* Motor do escritório: agentes, animação, câmera (arrastar / pinça / zoom) e toques. */
"use strict";
(function () {
  const A = window.EscritorioArte;
  const { T, RW, RH, GX, GY, M, COLUNAS, AISLE, PISOS, PELES, CABELOS, NOMES, CORES_CAMISA, ESTACOES, ETAPAS,
          hash, sombra, digitos, R, planks, desenharSala } = A;

  const VELOCIDADE = 44;            // pixels do mapa por segundo
  const AISLE_DESCANSO = 8;         // na sala de descanso o corredor livre é a linha 8 (a mesa ocupa a 7)
  const SEM_MOVIMENTO = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const aleat = (a, b) => a + Math.random() * (b - a);

  /* ---------- personagem ---------- */
  function pessoa(c, ag, t) {
    const x = Math.round(ag.x), y = Math.round(ag.y);
    const sentado = ag.pose === "sentado" && !ag.andando;
    const base = sentado ? y + 3 : y;
    const bob = ag.andando && ag.passo % 2 ? -1 : 0;
    const calca = "#2f3a55", sap = "#1d2230";
    R(c, "rgba(0,0,0,0.22)", x - 5, y - 1, 10, 2);
    if (!sentado) {                                      // pernas
      const a = ag.andando ? ag.passo % 2 : 0;
      R(c, calca, x - 4, base - 5, 3, 5 - a); R(c, calca, x + 1, base - 5, 3, 4 + a);
      R(c, sap, x - 4, base - 1 - a, 3, 1); R(c, sap, x + 1, base - 1 + a, 3, 1);
    }
    const cam = ag.camisa, dir = ag.dir;
    R(c, cam, x - 4, base - 11 + bob, 8, 6);             // tronco
    R(c, sombra(cam, -0.2), x - 4, base - 6 + bob, 8, 1);
    if (ag.terno) { R(c, "#fbfcfe", x - 1, base - 11 + bob, 2, 4); R(c, "#e5484d", x, base - 10 + bob, 1, 4); }
    // braços (balançam ao andar; "digitam" quando trabalham sentados)
    const digita = ag.trabalhando && Math.floor(t * 8) % 2;
    if (dir === "left" || dir === "right") {
      const lado = dir === "left" ? -5 : 4;
      R(c, sombra(cam, -0.1), x + lado, base - 11 + bob + (ag.andando ? (ag.passo % 2) : 0), 2, 5);
      R(c, ag.pele, x + lado, base - 6 + bob, 2, 1);
    } else {
      const ya = ag.trabalhando && (dir === "up") ? -2 : 0;
      R(c, sombra(cam, -0.1), x - 6, base - 11 + bob + ya + (digita ? 1 : 0), 2, 5);
      R(c, sombra(cam, -0.1), x + 4, base - 11 + bob + ya + (digita ? 0 : 1), 2, 5);
      R(c, ag.pele, x - 6, base - 6 + bob + ya, 2, 1); R(c, ag.pele, x + 4, base - 6 + bob + ya, 2, 1);
    }
    // cabeça
    const hy = base - 18 + bob;
    R(c, ag.pele, x - 4, hy, 8, 7);
    if (dir === "up") {
      R(c, ag.cabelo, x - 4, hy, 8, 6);
    } else if (dir === "down") {
      R(c, ag.cabelo, x - 4, hy, 8, 3); R(c, ag.cabelo, x - 4, hy + 3, 1, 2); R(c, ag.cabelo, x + 3, hy + 3, 1, 2);
      R(c, "#1a1d24", x - 2, hy + 4, 1, 2); R(c, "#1a1d24", x + 1, hy + 4, 1, 2);
    } else {
      const f = dir === "left" ? -1 : 1;
      R(c, ag.cabelo, x - 4, hy, 8, 3); R(c, ag.cabelo, f === -1 ? x + 1 : x - 4, hy + 3, 3, 3);
      R(c, "#1a1d24", f === -1 ? x - 3 : x + 2, hy + 4, 1, 2);
    }
    if (ag.terno) R(c, "#1a1d24", x - 3, hy + 4, 6, 1);   // óculos escuros do dono
  }

  function balao(c, cx, topo, tipo, t) {
    const w = 15, h = 10, bx = Math.round(cx - w / 2), by = Math.round(topo - h - 5);
    R(c, "#2a2f3a", bx, by + 1, w, h - 2); R(c, "#2a2f3a", bx + 1, by, w - 2, h);
    R(c, "#ffffff", bx + 1, by + 1, w - 2, h - 2); R(c, "#ffffff", bx + 2, by, w - 4, h);
    R(c, "#2a2f3a", Math.round(cx) - 1, by + h, 3, 1); R(c, "#ffffff", Math.round(cx), by + h - 1, 1, 2);
    if (tipo === "pensa") {
      const n = Math.floor(t * 3) % 3;
      for (let i = 0; i < 3; i++) R(c, i === n ? "#2a2f3a" : "#9aa3b2", bx + 3 + i * 4, by + 4, 2, 2);
    } else if (tipo === "espera") {                       // ampulheta
      R(c, "#2a2f3a", bx + 5, by + 2, 5, 1); R(c, "#2a2f3a", bx + 5, by + 7, 5, 1);
      R(c, "#e8a33a", bx + 6, by + 3, 3, 1); R(c, "#e8a33a", bx + 7, by + 4, 1, 1); R(c, "#e8a33a", bx + 6, by + 6, 3, 1);
    } else if (tipo === "alerta") {
      R(c, "#e5484d", bx + 7, by + 2, 2, 4); R(c, "#e5484d", bx + 7, by + 7, 2, 1);
    } else if (tipo === "ok") {
      R(c, "#30a46c", bx + 4, by + 5, 2, 2); R(c, "#30a46c", bx + 6, by + 6, 2, 2); R(c, "#30a46c", bx + 8, by + 3, 2, 3);
    }
  }

  /* ---------- efeitos de cada estação, quando há alguém trabalhando ---------- */
  function efeito(c, sala, etapa, t) {
    c.save(); c.translate(sala.px, sala.py);
    const e = ESTACOES[etapa];
    R(c, "rgba(255,226,120,0.22)", (e.tx - 1) * T, (e.ty - 1) * T + 4, 3 * T, 2 * T);  // luz no chão
    const f = Math.floor(t * 6);
    if (etapa === "roteiro") {                                    // texto aparecendo no monitor
      R(c, "#0e2a4a", 130, 50, 12, 6);
      for (let i = 0; i < 3; i++) R(c, "#bfe3ff", 131, 51 + i * 2, 3 + ((f + i * 3) % 7), 1);
    } else if (etapa === "montagem") {                            // linha do tempo andando
      R(c, "#12203a", 130, 146, 12, 6);
      R(c, "#30a46c", 131, 147, 4 + (f % 3), 1); R(c, "#f5a524", 131, 149, 6, 1); R(c, "#8e4ec6", 131, 151, 3 + ((f + 1) % 4), 1);
      R(c, "#ffdf70", 131 + (f % 11), 146, 1, 6);
    } else if (etapa === "narracao") {                            // ondas de voz
      for (let i = 0; i < 3; i++) {
        const fase = (t * 1.4 + i / 3) % 1;
        R(c, `rgba(255,255,255,${(1 - fase) * 0.8})`, 13 * T + 8 - 4 - fase * 10, 3 * T + 10, 2, 5);
        R(c, `rgba(255,255,255,${(1 - fase) * 0.8})`, 13 * T + 8 + 2 + fase * 10, 3 * T + 10, 2, 5);
      }
      R(c, "#e5484d", 12 * T + 8, 5 * T + 6, 2, 2);
    } else if (etapa === "cenas") {                               // rabiscos no quadro
      const n = Math.floor((t * 2) % 5);
      const cores = ["#3e63dd", "#e5484d", "#30a46c", "#f5a524", "#8e4ec6"];
      for (let i = 0; i <= n; i++) R(c, cores[i], 31 + i * 4, 136 + (i % 2) * 6, 3, 5 + (i % 3) * 2);
    } else if (etapa === "thumbnail") {                           // pintando a arte
      R(c, ["#3e63dd", "#e5484d", "#f5c542", "#30a46c"][f % 4], 191 + (f * 3) % 11, 149, 3, 3);
    } else if (etapa === "pesquisa") {                            // livro aberto
      R(c, "#f5c542", 3 * T + 12, 3 * T + 2 - (f % 2), 5, 4); R(c, "#fbfcfe", 3 * T + 13, 3 * T + 3 - (f % 2), 3, 2);
    }
    c.restore();
  }

  /* ---------- o escritório ---------- */
  function criar(canvas, op = {}) {
    const ctx = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0, H = 0;
    let salas = [], agentes = new Map(), estatico = null, mapaW = 0, mapaH = 0, chaveLayout = "";
    let primeiroLayout = true, estado = null, view = { s: 1, tx: 0, ty: 0 }, anim = null, tAnterior = performance.now(), parou = false;
    let selecionado = null;

    /* -- layout -- */
    function layout() {
      const canais = estado.canais;
      const lista = [{ tipo: "maestro", id: "maestro", nome: "Sala do Maestro" }, { tipo: "descanso", id: "descanso", nome: "Sala de descanso" }]
        .concat(canais.map((c, i) => ({ tipo: "canal", id: c.id, nome: c.nome, piso: PISOS[i % PISOS.length], idxCanal: i })));
      salas = lista.map((s, i) => ({ ...s, idx: i, px: (M + (i % COLUNAS) * (RW + GX)) * T, py: (M + Math.floor(i / COLUNAS) * (RH + GY)) * T }));
      const linhas = Math.ceil(salas.length / COLUNAS);
      mapaW = (M * 2 + COLUNAS * RW + (COLUNAS - 1) * GX) * T;
      mapaH = (M * 2 + linhas * RH + (linhas - 1) * GY) * T;
      estatico = document.createElement("canvas");
      estatico.width = mapaW; estatico.height = mapaH;
      const c = estatico.getContext("2d");
      planks(c, 0, 0, mapaW, mapaH);
      R(c, "rgba(0,0,0,0.12)", 0, 0, mapaW, 3); R(c, "rgba(0,0,0,0.12)", 0, 0, 3, mapaH);
      salas.forEach((s) => desenharSala(c, s));
    }

    const salaDe = (id) => salas.find((s) => s.id === id);
    const pxTile = (sala, tx, ty) => [sala.px + (tx + 0.5) * T, sala.py + (ty + 1) * T - 3];
    const linhaCorredor = (sala) => sala.py + ((sala.tipo === "descanso" ? AISLE_DESCANSO : AISLE) + 1) * T - 3;

    function novoAgente(sala, id, nome, i, extra = {}) {
      const h = hash(id);
      const [x, y] = pxTile(sala, 8, sala.tipo === "descanso" ? AISLE_DESCANSO : AISLE);
      return { id, sala, nome, x, y, dir: "down", passo: 0, dist: 0, rota: [], pose: "em_pe", andando: false, trabalhando: false,
               status: "ocioso", etapa: null, tVagar: aleat(1, 3), canal: nome,
               camisa: CORES_CAMISA[hash(sala.id) % CORES_CAMISA.length], pele: PELES[h % PELES.length], cabelo: CABELOS[(h >> 3) % CABELOS.length],
               ...extra };
    }

    function irPara(ag, tx, ty) {
      const [X, Y] = pxTile(ag.sala, tx, ty), ay = linhaCorredor(ag.sala);
      const pts = [];
      if (Math.abs(ag.x - X) < 1) pts.push([X, Y]);
      else { if (Math.abs(ag.y - ay) > 1) pts.push([ag.x, ay]); pts.push([X, ay]); pts.push([X, Y]); }
      ag.rota = SEM_MOVIMENTO ? [pts[pts.length - 1]] : pts;
    }

    /* -- estado vindo do servidor -- */
    function atualizar(novo) {
      estado = novo;
      const chave = estado.canais.map((c) => c.id).join("|");
      if (chave !== chaveLayout) {
        chaveLayout = chave; layout();
        const antigos = agentes; agentes = new Map();
        for (const s of salas) {
          if (s.tipo === "canal") agentes.set(s.id, antigos.get(s.id) && antigos.get(s.id).sala.id === s.id ? Object.assign(antigos.get(s.id), { sala: s }) : novoAgente(s, s.id, NOMES[s.idxCanal % NOMES.length]));
          if (s.tipo === "descanso") agentes.set("dono", novoAgente(s, "dono", "Você", 0, { terno: true, camisa: "#2a2f3a", pele: PELES[0], cabelo: CABELOS[0], canal: "Você" }));
        }
        if (primeiroLayout && W) { ajustar(true); primeiroLayout = false; }
      }
      for (const s of salas) {
        if (s.tipo !== "canal") continue;
        const ag = agentes.get(s.id), canal = estado.canais.find((c) => c.id === s.id);
        ag.canal = canal.nome;
        const v = estado.videos.find((x) => x.canal_id === s.id && (x.status === "em_producao" || x.status === "pausado") && x.etapa);
        const concluidos = estado.videos.filter((x) => x.canal_id === s.id && x.status === "agendado_no_canal").length;
        s.nv = 1 + Math.floor(concluidos / 3);
        const prontoAguardando = estado.pendentes.some((p) => p.canal_id === s.id);
        ag.video = v || null; ag.prontoAguardando = prontoAguardando;
        if (v) {
          ag.status = v.status === "pausado" ? "pausado" : "trabalhando";
          if (ag.etapa !== v.etapa) { ag.etapa = v.etapa; const e = ESTACOES[v.etapa]; irPara(ag, e.tx, e.ty); ag.chegou = false; }
        } else {
          ag.status = "ocioso";
          if (ag.etapa) { ag.etapa = null; ag.chegou = false; ag.trabalhando = false; ag.tVagar = 0.5; }
        }
      }
      const dono = agentes.get("dono");
      if (dono) dono.alerta = estado.pendentes.length > 0;
    }

    /* -- simulação -- */
    function passo(ag, dt) {
      if (ag.rota.length) {
        const [px, py] = ag.rota[0], dx = px - ag.x, dy = py - ag.y, d = Math.hypot(dx, dy), m = Math.min(d, VELOCIDADE * dt);
        if (d < 0.5) { ag.rota.shift(); return; }
        ag.x += (dx / d) * m; ag.y += (dy / d) * m;
        ag.dir = Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? "left" : "right") : (dy < 0 ? "up" : "down");
        ag.andando = true; ag.pose = "em_pe"; ag.trabalhando = false;
        ag.dist += m; ag.passo = Math.floor(ag.dist / 4);
        return;
      }
      ag.andando = false;
      if (ag.etapa) {                                         // chegou à estação: assume a pose de trabalho
        const e = ESTACOES[ag.etapa]; ag.dir = e.olha; ag.pose = e.pose; ag.chegou = true;
        ag.trabalhando = ag.status === "trabalhando";
        return;
      }
      ag.pose = "em_pe"; ag.trabalhando = false;
      ag.tVagar -= dt;                                        // sem trabalho: passeia devagar pela própria sala
      if (ag.tVagar <= 0) {
        ag.tVagar = aleat(4, 9);
        const linha = ag.sala.tipo === "descanso" ? AISLE_DESCANSO : AISLE;
        irPara(ag, Math.floor(aleat(4, 12)), linha);
      }
    }

    /* -- desenho -- */
    const rectBandeja = (s) => [s.px + T + 8, s.py + 4 * T, 34, 26];

    function dinamico(t) {
      // efeitos nas estações com agente trabalhando
      for (const ag of agentes.values()) if (ag.chegou && ag.trabalhando && ag.etapa) efeito(ctx, ag.sala, ag.etapa, t);
      // sala do maestro: agenda do dia e bandeja de aprovação
      const m = salas.find((s) => s.tipo === "maestro");
      if (m) {
        ctx.save(); ctx.translate(m.px, m.py);
        const hoje = estado.videos.filter((v) => v.producao_em.slice(0, 10) === estado.hoje).sort((a, b) => a.producao_em.localeCompare(b.producao_em)).slice(0, 4);
        hoje.forEach((v, i) => {
          const y = 10 + i * 7;
          const cor = { agendado: "#9aa3b2", em_producao: "#4a90ff", pausado: "#f0a94a", falhou: "#e5484d" }[v.status] || "#4cc9a0";
          R(ctx, cor, 91, y + 1, 3, 3); digitos(ctx, v.producao_em.slice(11, 16), 97, y, "#e8ecf4");
        });
        if (!hoje.length) R(ctx, "#4a5565", 96, 22, 40, 1);
        const n = estado.pendentes.length;
        if (n) {
          const b = 1 + Math.floor((Math.sin(t * 4) + 1) / 2);
          R(ctx, "#2a2f3a", T + 8 + 28 - 1, 4 * T - 8 - 1, 12, 12); R(ctx, "#f0a94a", T + 8 + 28, 4 * T - 8, 10, 10);
          digitos(ctx, String(Math.min(n, 9)), T + 8 + 31, 4 * T - 6 + (b === 2 ? 0 : 0), "#1a1100");
        }
        ctx.restore();
      }
      // personagens, de trás para a frente
      const todos = [...agentes.values()].sort((a, b) => a.y - b.y);
      for (const ag of todos) {
        pessoa(ctx, ag, t);
        let b = null;
        if (ag.id === "dono") b = ag.alerta ? "alerta" : null;
        else if (ag.status === "pausado") b = "espera";
        else if (ag.status === "trabalhando" && ag.chegou) b = "pensa";
        else if (ag.prontoAguardando) b = "ok";
        if (b) balao(ctx, ag.x, ag.y - (ag.pose === "sentado" && !ag.andando ? 15 : 18), b, t);
      }
    }

    function chip(texto, x, y, { fundo = "rgba(255,248,235,0.92)", cor = "#6b5a45", fonte = '600 12px Georgia, "Times New Roman", serif', ponto = null } = {}) {
      ctx.font = fonte;
      const w = ctx.measureText(texto).width + 14 + (ponto ? 12 : 0), h = 20;
      ctx.fillStyle = "rgba(0,0,0,0.18)"; roundRect(x + 1, y - h + 2, w, h, 10); ctx.fill();
      ctx.fillStyle = fundo; roundRect(x, y - h, w, h, 10); ctx.fill();
      let tx = x + 7;
      if (ponto) { ctx.fillStyle = ponto; ctx.beginPath(); ctx.arc(x + 12, y - h / 2, 4, 0, 7); ctx.fill(); tx += 12; }
      ctx.fillStyle = cor; ctx.textBaseline = "middle"; ctx.fillText(texto, tx, y - h / 2 + 0.5);
      return w;
    }
    function roundRect(x, y, w, h, r) {
      ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
      ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
    }
    const paraTela = (mx, my) => [view.tx + mx * view.s, view.ty + my * view.s];

    function etiquetas() {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      for (const s of salas) {
        const [sx, sy] = paraTela(s.px, s.py);
        const texto = s.tipo === "canal" ? `${s.nome} · Nv ${s.nv || 1}` : s.nome;
        s.chip = [sx, sy - 6, chip(texto, sx + 2, sy - 6)];
      }
      if (view.s >= 1.5) for (const ag of agentes.values()) {
        const [ax, ay] = paraTela(ag.x, ag.y - (ag.pose === "sentado" && !ag.andando ? 36 : 42));
        const ponto = ag.id === "dono" ? "#30a46c" : { trabalhando: "#30a46c", pausado: "#f0a94a", ocioso: "#9aa3b2" }[ag.status];
        ctx.font = '600 11px system-ui, sans-serif';
        const w = ctx.measureText(ag.id === "dono" ? "Você" : ag.canal).width + 26;
        chip(ag.id === "dono" ? "Você" : ag.canal, ax - w / 2, ay, { fundo: "rgba(20,22,28,0.88)", cor: "#fff", fonte: '600 11px system-ui, sans-serif', ponto });
      }
    }

    function quadro(agora) {
      const dt = Math.min(0.05, (agora - tAnterior) / 1000); tAnterior = agora;
      const t = agora / 1000;
      if (anim) {
        const p = Math.min(1, (agora - anim.t0) / anim.dur), e = 1 - Math.pow(1 - p, 3);
        view = { s: anim.de.s + (anim.para.s - anim.de.s) * e, tx: anim.de.tx + (anim.para.tx - anim.de.tx) * e, ty: anim.de.ty + (anim.para.ty - anim.de.ty) * e };
        if (p >= 1) anim = null;
      }
      if (estado && estatico) {
        for (const ag of agentes.values()) passo(ag, dt);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.fillStyle = "#f3e6cf"; ctx.fillRect(0, 0, W, H);
        ctx.imageSmoothingEnabled = false;
        ctx.setTransform(dpr * view.s, 0, 0, dpr * view.s, dpr * view.tx, dpr * view.ty);
        ctx.drawImage(estatico, 0, 0);
        dinamico(t);
        etiquetas();
        if (selecionado && agentes.get(selecionado)) op.onPosicao && op.onPosicao(paraTela(agentes.get(selecionado).x, agentes.get(selecionado).y));
      }
      if (!parou) requestAnimationFrame(quadro);
    }

    /* -- câmera -- */
    function limitar() {
      const mw = mapaW * view.s, mh = mapaH * view.s, folga = 60;
      view.tx = mw <= W ? (W - mw) / 2 : Math.min(folga, Math.max(W - mw - folga, view.tx));
      view.ty = mh <= H ? (H - mh) / 2 : Math.min(folga, Math.max(H - mh - folga, view.ty));
    }
    const sMin = () => Math.min(W / mapaW, H / mapaH) * 0.98;
    function ajustar(imediato) {
      if (!mapaW) return;
      const s = sMin(); const para = { s, tx: (W - mapaW * s) / 2, ty: (H - mapaH * s) / 2 };
      if (imediato) { view = para; anim = null; } else irPara2(para);
    }
    function irPara2(para, dur = 450) { anim = { de: { ...view }, para, t0: performance.now(), dur }; }
    function zoomEm(fator, cx = W / 2, cy = H / 2, imediato = true) {
      const s = Math.max(sMin(), Math.min(10, view.s * fator)), k = s / view.s;
      const novo = { s, tx: cx - (cx - view.tx) * k, ty: cy - (cy - view.ty) * k };
      if (imediato) { view = novo; limitar(); anim = null; } else irPara2(novo);
    }
    function focarSala(s) {
      const sc = Math.min(10, (W * 0.96) / (RW * T));
      const para = { s: sc, tx: W / 2 - (s.px + (RW * T) / 2) * sc, ty: H / 2 - (s.py + (RH * T) / 2) * sc };
      irPara2(para, 500);
    }

    /* -- toques / ponteiro -- */
    const ponteiros = new Map(); let inicio = null, ultimoPinca = null;
    canvas.addEventListener("pointerdown", (e) => {
      canvas.setPointerCapture(e.pointerId);
      ponteiros.set(e.pointerId, { x: e.clientX, y: e.clientY });
      inicio = { x: e.clientX, y: e.clientY, t: performance.now(), mov: 0, n: ponteiros.size }; anim = null;
      ultimoPinca = null;
    });
    canvas.addEventListener("pointermove", (e) => {
      const p = ponteiros.get(e.pointerId); if (!p) return;
      const r = canvas.getBoundingClientRect();
      if (ponteiros.size === 1) {
        view.tx += e.clientX - p.x; view.ty += e.clientY - p.y; limitar();
        if (inicio) inicio.mov += Math.abs(e.clientX - p.x) + Math.abs(e.clientY - p.y);
      } else if (ponteiros.size === 2) {
        p.x = e.clientX; p.y = e.clientY;
        const [a, b] = [...ponteiros.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2 - r.left, my = (a.y + b.y) / 2 - r.top;
        if (ultimoPinca) { zoomEm(d / ultimoPinca.d, mx, my); view.tx += mx - ultimoPinca.mx; view.ty += my - ultimoPinca.my; limitar(); }
        ultimoPinca = { d, mx, my }; if (inicio) inicio.mov += 99;
      }
      p.x = e.clientX; p.y = e.clientY;
    });
    function soltar(e) {
      const tinha = ponteiros.has(e.pointerId); ponteiros.delete(e.pointerId); ultimoPinca = null;
      if (tinha && inicio && inicio.n === 1 && inicio.mov < 8 && performance.now() - inicio.t < 450 && ponteiros.size === 0) toque(e);
      if (!ponteiros.size) inicio = null;
    }
    canvas.addEventListener("pointerup", soltar); canvas.addEventListener("pointercancel", soltar);
    canvas.addEventListener("wheel", (e) => { e.preventDefault(); const r = canvas.getBoundingClientRect(); zoomEm(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top); }, { passive: false });

    function toque(e) {
      const r = canvas.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top;
      const mx = (sx - view.tx) / view.s, my = (sy - view.ty) / view.s;
      for (const s of salas) if (s.chip && sx >= s.chip[0] && sx <= s.chip[0] + s.chip[2] + 4 && sy <= s.chip[1] + 2 && sy >= s.chip[1] - 24) return focarSala(s);
      for (const ag of [...agentes.values()].sort((a, b) => b.y - a.y)) {
        if (Math.abs(mx - ag.x) < 9 && my < ag.y + 2 && my > ag.y - 22) { selecionar(ag.id); return; }
      }
      const m = salas.find((s) => s.tipo === "maestro");
      if (m) { const [bx, by, bw, bh] = rectBandeja(m); if (mx >= bx - 4 && mx <= bx + bw + 14 && my >= by - 12 && my <= by + bh + 2) { op.onAprovar && op.onAprovar(); return; } }
      for (const s of salas) if (mx >= s.px && mx <= s.px + RW * T && my >= s.py && my <= s.py + RH * T) { if (view.s < 1.5) focarSala(s); break; }
      selecionar(null);
    }
    function selecionar(id) {
      selecionado = id;
      if (!id) { op.onAgente && op.onAgente(null); return; }
      const ag = agentes.get(id), v = ag.video;
      op.onAgente && op.onAgente({
        nome: ag.nome, canal: ag.id === "dono" ? "Dono da fábrica" : ag.canal, dono: ag.id === "dono",
        status: ag.status, verbo: ag.etapa ? ESTACOES[ag.etapa].verbo : (ag.prontoAguardando ? "terminou um vídeo — aguardando você" : "descansando entre vídeos"),
        tema: v ? v.tema : null, progresso: v ? v.etapas_feitas / v.etapas_total : null, retomar_em: v && v.retomar_em, pendentes: estado.pendentes.length,
      });
    }

    function redimensionar() {
      const r = canvas.getBoundingClientRect();
      const antes = W; W = Math.max(1, r.width); H = Math.max(1, r.height);
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      if (!antes && mapaW) ajustar(true); else if (mapaW) { limitar(); }
    }
    const ro = new ResizeObserver(redimensionar); ro.observe(canvas); redimensionar();
    document.addEventListener("visibilitychange", () => { tAnterior = performance.now(); });
    requestAnimationFrame(quadro);

    return {
      atualizar, ajustar: () => ajustar(false), zoom: (f) => zoomEm(f, W / 2, H / 2, false),
      focarCanal: (id) => { const s = salaDe(id); if (s) focarSala(s); },
      fechar: () => { selecionado = null; }, destruir: () => { parou = true; ro.disconnect(); },
    };
  }

  window.Escritorio = { criar };
})();
