/* Escritório da fábrica — pixel art vista de cima.
 * Cada canal tem a sua sala; cada vídeo em produção é um agente que anda até a estação da etapa atual.
 * Tudo é desenhado em canvas (sem imagens): peças em retângulos, personagens em sprites procedurais.
 */
"use strict";
(function () {
  const T = 16;                  // lado do tile, em pixels do mapa
  const RW = 16, RH = 12;        // sala: 16 x 12 tiles
  const GX = 2, GY = 3, M = 2;   // corredor horizontal/vertical e margem, em tiles
  const COLUNAS = 2;
  const AISLE = 7;               // linha do corredor interno da sala (livre de móveis)

  /* ---------- cores ---------- */
  const PISOS = [               // [a, b] = quadriculado do piso de cada canal
    ["#8f94e8", "#868be0"], ["#d9a45f", "#cf9a55"], ["#8fcf7b", "#86c672"],
    ["#f2a9c5", "#ec9fbc"], ["#b8bbc2", "#b0b3ba"], ["#9fd2e0", "#96c9d8"], ["#e9c36e", "#e0ba63"],
  ];
  const PELES = ["#f2c9a0", "#e3a977", "#c98a5b", "#8d5a3a", "#f6d5b5"];
  const CABELOS = ["#2b2f38", "#5a3418", "#8a4b1f", "#d9b04c", "#a33a2a", "#3a2a5e"];
  const NOMES = ["Kátia", "Malu", "Bruno", "Rafa", "Duda", "Léo", "Nina", "Téo", "Bia", "Caio"];
  const CORES_CAMISA = ["#3e63dd", "#e5484d", "#30a46c", "#d9822b", "#8e4ec6", "#0a8aa6", "#c2417a"];

  const hash = (txt) => { let h = 7; for (const c of String(txt)) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h; };

  function sombra(hex, k) {     // k < 0 escurece, k > 0 clareia
    const n = parseInt(hex.slice(1), 16);
    const f = (v) => Math.max(0, Math.min(255, Math.round(k > 0 ? v + (255 - v) * k : v * (1 + k))));
    return "#" + [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => f(v).toString(16).padStart(2, "0")).join("");
  }

  /* ---------- fonte de dígitos 3x5 (para horas e contadores dentro do mapa) ---------- */
  const DIG = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001001001",
    "8": "111101111101111", "9": "111101111001111", ":": "000010000010000",
  };
  function digitos(c, txt, x, y, cor) {
    c.fillStyle = cor;
    for (const ch of txt) {
      const g = DIG[ch]; if (!g) { x += 2; continue; }
      for (let i = 0; i < 15; i++) if (g[i] === "1") c.fillRect(x + (i % 3), y + Math.floor(i / 3), 1, 1);
      x += 4;
    }
  }

  const R = (c, cor, x, y, w, h) => { c.fillStyle = cor; c.fillRect(Math.round(x), Math.round(y), w, h); };

  /* ---------- peças (coordenadas em pixels, relativas à sala) ---------- */
  function planks(c, x, y, w, h) {               // corredores: tábuas de madeira
    R(c, "#d9b27c", x, y, w, h);
    for (let yy = 0; yy < h; yy += 8) {
      R(c, "#c99d64", x, y + yy, w, 1);
      for (let xx = ((yy / 8) % 2) * 12; xx < w; xx += 24) R(c, "#c99d64", x + xx, y + yy, 1, 8);
    }
  }
  function janela(c, x, y, w) {
    R(c, "#9a8670", x, y, w, 12); R(c, "#bfe3f5", x + 1, y + 1, w - 2, 10);
    R(c, "#e8f6ff", x + 1, y + 1, w - 2, 3);
    R(c, "#9a8670", x + Math.floor(w / 2), y, 1, 12);
  }
  function relogio(c, x, y) {
    R(c, "#6b5a45", x, y, 9, 9); R(c, "#fff8ea", x + 1, y + 1, 7, 7);
    R(c, "#333", x + 4, y + 2, 1, 3); R(c, "#333", x + 4, y + 4, 3, 1);
  }
  function planta(c, x, y) {
    R(c, "#7a5230", x + 2, y + 8, 8, 6); R(c, "#9a6b3d", x + 2, y + 8, 8, 2);
    R(c, "#2f8f4e", x + 5, y, 2, 9); R(c, "#3fae63", x, y + 2, 5, 3); R(c, "#3fae63", x + 7, y + 3, 5, 3);
    R(c, "#58c97d", x + 3, y, 3, 3); R(c, "#58c97d", x + 6, y + 1, 3, 2);
  }
  function estante(c, x, y, w) {                 // estante de livros encostada na parede
    R(c, "#6f4a2a", x, y, w, 30); R(c, "#8a6038", x, y, w, 2);
    const livros = ["#e5484d", "#3e63dd", "#30a46c", "#f5a524", "#8e4ec6", "#0a8aa6", "#c2417a"];
    for (let r = 0; r < 3; r++) {
      const yy = y + 3 + r * 9;
      R(c, "#4f341c", x + 1, yy + 7, w - 2, 2);
      let xx = x + 2, i = r * 2;
      while (xx < x + w - 4) {
        const lw = 2 + ((i * 7) % 3), lh = 5 + ((i * 5) % 3);
        R(c, livros[i % livros.length], xx, yy + 7 - lh, lw, lh); xx += lw + 1; i++;
      }
    }
  }
  function mesa(c, x, y, w, h, comMonitor) {     // mesa branca vista de cima
    R(c, "#b9bdc8", x, y + h - 2, w, 2);
    R(c, "#f4f5f8", x, y, w, h - 2); R(c, "#dfe2ea", x, y, w, 1);
    if (comMonitor) {
      const mx = x + Math.floor(w / 2) - 7;
      R(c, "#2a2f3a", mx, y + 1, 14, 9); R(c, "#4aa8ff", mx + 1, y + 2, 12, 6);
      R(c, "#2a2f3a", mx + 5, y + 10, 4, 2);
      R(c, "#cfd3dc", mx + 1, y + h - 5, 12, 2);                 // teclado
      R(c, "#f5c542", x + w - 7, y + 2, 4, 3); R(c, "#8a8f9c", x + w - 6, y + 5, 2, 3);  // abajur
      R(c, "#e5484d", x + 3, y + 3, 3, 3);                        // caneca
    }
  }
  function cadeira(c, x, y) {
    R(c, "#2a2f3a", x + 1, y + 2, 10, 7); R(c, "#3a4252", x + 2, y + 3, 8, 5);
    R(c, "#8a6a3a", x + 3, y + 5, 6, 3);
    R(c, "#1a1d24", x + 1, y + 9, 3, 2); R(c, "#1a1d24", x + 8, y + 9, 3, 2);
  }
  function cabine(c, x, y, w, h) {               // cabine de gravação: caixa escura com microfone
    R(c, "#1d2128", x, y, w, h); R(c, "#2d3340", x + 2, y + 2, w - 4, h - 6);
    R(c, "#3a4252", x + 2, y + 2, w - 4, 2);
    R(c, "#0f1217", x + Math.floor(w / 2) - 6, y + h - 4, 12, 4);        // porta
    const mx = x + Math.floor(w / 2);
    R(c, "#9aa3b2", mx - 1, y + 9, 2, 9); R(c, "#cfd6e2", mx - 3, y + 6, 6, 5); R(c, "#5a6270", mx - 2, y + 7, 4, 3);
  }
  function cavalete(c, x, y) {                   // quadro branco no cavalete
    R(c, "#6f4a2a", x + 2, y + 17, 2, 8); R(c, "#6f4a2a", x + 20, y + 17, 2, 8);
    R(c, "#7a5230", x, y, 24, 18); R(c, "#fbfcfe", x + 1, y + 1, 22, 16);
  }
  function mesaArte(c, x, y, w) {                // mesa de arte com tintas
    R(c, "#a87a4c", x, y + 12, w, 2); R(c, "#d9a875", x, y, w, 12);
    R(c, "#fbfcfe", x + 3, y + 2, 14, 8); R(c, "#3e63dd", x + 5, y + 4, 10, 4); R(c, "#f5c542", x + 12, y + 3, 3, 3);
    ["#e5484d", "#30a46c", "#f5c542", "#8e4ec6"].forEach((cor, i) => R(c, cor, x + w - 16 + i * 4, y + 3, 3, 3));
  }
  function tapete(c, x, y, w, h, cor) {
    R(c, sombra(cor, -0.25), x, y, w, h); R(c, cor, x + 1, y + 1, w - 2, h - 2);
    for (let xx = x + 4; xx < x + w - 6; xx += 8) R(c, sombra(cor, 0.35), xx, y + Math.floor(h / 2), 5, 2);
  }
  function sofa(c, x, y, w) {
    R(c, "#9a6c3e", x, y, w, 15); R(c, "#c99a6b", x + 1, y + 1, w - 2, 12); R(c, "#b0824f", x, y, w, 4);
    R(c, "#9a6c3e", x, y, 3, 15); R(c, "#9a6c3e", x + w - 3, y, 3, 15);
    for (let i = x + 5; i < x + w - 6; i += 18) { R(c, "#dcb283", i, y + 5, 16, 8); R(c, "#e8c498", i, y + 5, 16, 2); }
  }
  function mesaRedonda(c, x, y) {
    R(c, "#b0824f", x + 2, y + 2, 28, 16); R(c, "#d9a875", x, y, 32, 16); R(c, "#e8bf90", x + 3, y + 2, 26, 11);
    R(c, "#7a5ad8", x + 14, y + 5, 4, 4);
  }
  function puff(c, x, y, cor) { R(c, sombra(cor, -0.2), x, y + 2, 9, 8); R(c, cor, x, y, 9, 8); }
  function quadroAgenda(c, x, y) {
    R(c, "#6f4a2a", x, y, 66, 34); R(c, "#2f3a4a", x + 2, y + 2, 62, 30);
  }
  function bandeja(c, x, y) {                    // caixa de aprovação
    R(c, "#a87a4c", x, y + 10, 34, 12); R(c, "#c99a6b", x, y + 4, 34, 8); R(c, "#8a6038", x, y + 18, 34, 4);
    R(c, "#fbfcfe", x + 3, y + 1, 26, 5); R(c, "#e8ecf4", x + 5, y + 3, 26, 4);
  }
  function cofre(c, x, y) {
    R(c, "#4a5565", x, y, 28, 30); R(c, "#6a7689", x + 2, y + 2, 24, 26); R(c, "#2f3a4a", x + 4, y + 4, 20, 22);
    R(c, "#cfd6e2", x + 9, y + 9, 10, 10); R(c, "#4a5565", x + 12, y + 12, 4, 4);
    R(c, "#f5c542", x + 6, y + 24, 16, 3); R(c, "#ffdf70", x + 8, y + 22, 12, 3);
  }
  function podio(c, x, y) {                      // pódio do maestro
    R(c, "#3a2a5e", x, y + 4, 22, 10); R(c, "#5a3f9a", x + 1, y, 20, 6); R(c, "#fbfcfe", x + 5, y + 1, 12, 4);
  }

  /* ---------- salas ---------- */
  function pisoDaSala(c, tipo, cor) {
    const [a, b] = tipo === "descanso" ? ["#f6f7fb", "#eceef5"] : tipo === "maestro" ? ["#d6c7e8", "#cdbde1"] : cor;
    for (let ty = 3; ty < RH; ty++) for (let tx = 0; tx < RW; tx++) {
      R(c, (tx + ty) % 2 ? b : a, tx * T, ty * T, T, T);
      R(c, "rgba(0,0,0,0.05)", tx * T, ty * T, T, 1); R(c, "rgba(0,0,0,0.05)", tx * T, ty * T, 1, T);
    }
    const parede = tipo === "descanso" ? "#e9edf5" : sombra(a, 0.3);
    R(c, parede, 0, 0, RW * T, 3 * T);
    R(c, sombra(parede, -0.14), 0, 3 * T - 6, RW * T, 6);        // rodapé
    R(c, "rgba(0,0,0,0.12)", 0, 3 * T, RW * T, 2);
    R(c, "#4a4034", 0, 0, 2, RH * T); R(c, "#4a4034", RW * T - 2, 0, 2, RH * T); R(c, "#4a4034", 0, RH * T - 2, RW * T, 2);
    R(c, "#4a4034", 0, 0, RW * T, 2);
    R(c, "rgba(0,0,0,0.1)", RW * T - 4, 0, 2, RH * T);
  }

  function desenharSala(c, sala) {
    c.save(); c.translate(sala.px, sala.py);
    pisoDaSala(c, sala.tipo, sala.piso);
    if (sala.tipo === "canal") {
      tapete(c, 4 * T, 6 * T, 8 * T, 3 * T, sombra(sala.piso[0], -0.14));
      janela(c, 7 * T, 8, 18); janela(c, 10 * T + 4, 8, 18); relogio(c, 8 * T + 4, 24);
      estante(c, T, 2, 5 * T - 2);
      mesa(c, 6 * T + 8, 3 * T, 4 * T, 2 * T, true); cadeira(c, 8 * T + 2, 5 * T);
      cabine(c, 12 * T, 3 * T, 3 * T, 3 * T);
      cavalete(c, 2 * T - 4, 8 * T + 4);
      mesa(c, 6 * T + 8, 9 * T, 4 * T, 2 * T - 2, true); cadeira(c, 8 * T + 2, 8 * T);
      mesaArte(c, 12 * T - 4, 9 * T + 2, 4 * T);
      planta(c, T - 2, 10 * T - 4); planta(c, 15 * T - 10, 7 * T + 2);
      R(c, "rgba(255,255,255,0.35)", 6 * T + 8, RH * T - 2, 2 * T, 2);                          // porta
    } else if (sala.tipo === "descanso") {
      janela(c, 2 * T, 8, 18); janela(c, 12 * T, 8, 18); relogio(c, 8 * T - 4, 20);
      estante(c, 5, 2, 3 * T); estante(c, 13 * T - 5, 2, 3 * T);
      tapete(c, 3 * T, 5 * T + 8, 10 * T, 6 * T - 8, "#cdb8f0");
      sofa(c, 5 * T, 4 * T + 2, 6 * T); mesaRedonda(c, 7 * T, 6 * T + 8);
      sofa(c, 5 * T, 9 * T + 4, 6 * T);
      puff(c, 3 * T + 4, 7 * T, "#4a90ff"); puff(c, 12 * T - 4, 7 * T, "#a46cf0"); puff(c, 3 * T + 4, 9 * T, "#ff7ab0"); puff(c, 12 * T - 4, 9 * T, "#4a90ff");
      planta(c, T, 10 * T - 4); planta(c, 14 * T, 10 * T - 4);
    } else {                                    // sala do maestro
      janela(c, 2 * T, 8, 18); janela(c, 12 * T, 8, 18);
      quadroAgenda(c, 5 * T + 7, 6);
      tapete(c, 3 * T, 5 * T + 8, 10 * T, 5 * T, "#b79ae0");
      podio(c, 7 * T + 4, 6 * T + 8);
      bandeja(c, T + 8, 4 * T); cofre(c, 12 * T + 8, 4 * T - 4);
      planta(c, T, 10 * T - 4); planta(c, 14 * T, 10 * T - 4);
    }
    c.restore();
  }

  /* ---------- estações (tiles locais): onde o agente fica, para onde olha e o que faz ---------- */
  const ESTACOES = {
    pesquisa:  { tx: 3,  ty: 3, olha: "up",    pose: "em_pe",    verbo: "pesquisando na estante" },
    roteiro:   { tx: 8,  ty: 5, olha: "up",    pose: "sentado",  verbo: "escrevendo o roteiro" },
    narracao:  { tx: 13, ty: 6, olha: "up",    pose: "em_pe",    verbo: "gravando a narração" },
    cenas:     { tx: 4,  ty: 9, olha: "left",  pose: "em_pe",    verbo: "desenhando as cenas" },
    montagem:  { tx: 8,  ty: 8, olha: "down",  pose: "sentado",  verbo: "montando o vídeo" },
    thumbnail: { tx: 13, ty: 8, olha: "down",  pose: "em_pe",    verbo: "criando a thumbnail" },
  };
  const ETAPAS = Object.keys(ESTACOES);

  window.EscritorioArte = {
    T, RW, RH, GX, GY, M, COLUNAS, AISLE, PISOS, PELES, CABELOS, NOMES, CORES_CAMISA, ESTACOES, ETAPAS,
    hash, sombra, digitos, R, planks, desenharSala,
  };
})();
