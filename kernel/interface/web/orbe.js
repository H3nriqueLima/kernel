// A orbe: a forma viva do K.E.R.N.E.L.
//
// É um círculo cujo raio muda a cada ângulo e a cada instante. Três ondas lentas dão o
// "respirar"; quando ele fala, o volume da voz estica a forma e cada faixa de frequência
// empurra um pedaço do contorno. Cada estado (ocioso, explorando, pesquisando, pensando,
// falando, pausado, estudando) é só um conjunto de números: amplitude, velocidade e cor. A orbe
// desliza de um conjunto para o outro, então nenhuma mudança é brusca.
"use strict";

const ESTADOS = {
  //             ondulação  velocidade  matiz  saturação  brilho  satélites
  ocioso:     { amp: 0.035, vel: 0.35, cor: 182, sat: 85, luz: 1.0, sat_n: 0 },
  explorando: { amp: 0.060, vel: 0.85, cor: 162, sat: 85, luz: 1.1, sat_n: 3 },
  pesquisando: { amp: 0.070, vel: 1.15, cor: 38, sat: 88, luz: 1.12, sat_n: 2 },   // âmbar: está fora, na internet
  pensando:   { amp: 0.085, vel: 1.70, cor: 200, sat: 90, luz: 1.15, sat_n: 0 },
  falando:    { amp: 0.045, vel: 0.90, cor: 182, sat: 90, luz: 1.25, sat_n: 0 },
  estudando:  { amp: 0.050, vel: 0.60, cor: 262, sat: 75, luz: 1.1, sat_n: 1 },
  pausado:    { amp: 0.012, vel: 0.10, cor: 215, sat: 18, luz: 0.6, sat_n: 0 },
  alerta:     { amp: 0.030, vel: 0.40, cor: 40, sat: 90, luz: 1.0, sat_n: 0 },
  desligado:  { amp: 0.0, vel: 0.0, cor: 215, sat: 0, luz: 0.3, sat_n: 0 },
};
const PONTOS = 160;
const FAIXAS = 24;

class Orbe {
  constructor(tela) {
    this.tela = tela;
    this.ctx = tela.getContext("2d");
    this.alvo = "ocioso";
    this.atual = { ...ESTADOS.ocioso };
    this.nivel = 0;                       // volume da voz agora, de 0 a 1
    this.faixas = new Float32Array(FAIXAS); // espectro da voz agora
    this.fonte = null;                    // função que devolve {nivel, faixas} enquanto ele fala
    this.fase = 0;
    this.antes = performance.now();
    this.parado = matchMedia("(prefers-reduced-motion: reduce)").matches;
    new ResizeObserver(() => this.ajustar()).observe(tela.parentElement);
    this.ajustar();
    requestAnimationFrame((t) => this.quadro(t));
  }

  estado(nome) { this.alvo = ESTADOS[nome] ? nome : "ocioso"; }

  ajustar() {
    const caixa = this.tela.parentElement.getBoundingClientRect();
    // A tela é maior que a caixa (e passa por cima do que está em volta) para o halo nunca ser cortado.
    const lado = Math.max(180, Math.min(Math.min(caixa.width, caixa.height) * 1.6, caixa.width * 1.25));
    const densidade = Math.min(window.devicePixelRatio || 1, 2);
    this.tela.style.width = this.tela.style.height = `${lado}px`;
    this.tela.width = this.tela.height = Math.round(lado * densidade);
    this.lado = this.tela.width;
  }

  // raio do contorno no ângulo a (em fração do raio base)
  raio(a, fase, amp, deslocamento) {
    const ondas = 0.6 * Math.sin(2 * a + fase + deslocamento)
                + 0.4 * Math.sin(3 * a - 1.3 * fase + 1 + deslocamento * 2)
                + 0.3 * Math.sin(5 * a + 0.7 * fase + 2 - deslocamento);
    // o espectro é espelhado: graves embaixo, agudos em cima, igual dos dois lados
    const posicao = Math.abs(Math.sin(a / 2 + Math.PI / 4)) * (FAIXAS - 1);
    const i = Math.floor(posicao), resto = posicao - i;
    const faixa = this.faixas[i] * (1 - resto) + this.faixas[Math.min(i + 1, FAIXAS - 1)] * resto;
    return 1 + amp * ondas + this.nivel * (0.07 + 0.30 * faixa);
  }

  contorno(cx, cy, base, fase, amp, deslocamento) {
    const c = this.ctx;
    c.beginPath();
    for (let p = 0; p <= PONTOS; p++) {
      const a = (p / PONTOS) * Math.PI * 2;
      const r = base * this.raio(a, fase, amp, deslocamento);
      const x = cx + r * Math.cos(a - Math.PI / 2), y = cy + r * Math.sin(a - Math.PI / 2);
      p ? c.lineTo(x, y) : c.moveTo(x, y);
    }
    c.closePath();
  }

  quadro(agora) {
    const dt = Math.min(0.05, (agora - this.antes) / 1000);
    this.antes = agora;
    const alvo = ESTADOS[this.alvo], e = this.atual;
    for (const k of Object.keys(alvo)) e[k] += (alvo[k] - e[k]) * Math.min(1, dt * 3.5);
    this.fase += dt * e.vel * (this.parado ? 0.15 : 1);

    // a voz: sobe depressa, desce devagar, como um ponteiro de volume
    const lido = this.fonte ? this.fonte(agora) : null;
    const nivelAlvo = lido ? lido.nivel : 0;
    this.nivel += (nivelAlvo - this.nivel) * Math.min(1, dt * (nivelAlvo > this.nivel ? 22 : 7));
    for (let i = 0; i < FAIXAS; i++) {
      const v = lido ? lido.faixas[i] : 0;
      this.faixas[i] += (v - this.faixas[i]) * Math.min(1, dt * 16);
    }

    const c = this.ctx, L = this.lado, cx = L / 2, cy = L / 2;
    const base = L * 0.2 * (1 + 0.012 * Math.sin(agora / 1600));
    const tom = (d, s, l, a) => `hsla(${e.cor + d}, ${e.sat * s}%, ${l}%, ${a * e.luz})`;
    c.clearRect(0, 0, L, L);
    c.globalCompositeOperation = "lighter";

    // halo
    const halo = c.createRadialGradient(cx, cy, base * 0.6, cx, cy, Math.min(L / 2, base * (1.8 + this.nivel * 0.6)));
    halo.addColorStop(0, tom(0, 1, 55, 0.20 + this.nivel * 0.25));
    halo.addColorStop(1, tom(0, 1, 50, 0));
    c.fillStyle = halo;
    c.fillRect(0, 0, L, L);

    // três corpos sobrepostos, cada um um pouco fora de fase: dá a impressão de líquido
    for (const [desl, escala, dCor, alfa] of [[0, 1.0, 0, 0.55], [2.1, 0.94, 28, 0.38], [4.2, 1.05, -22, 0.22]]) {
      this.contorno(cx, cy, base * escala, this.fase, e.amp, desl);
      const corpo = c.createRadialGradient(cx - base * 0.25, cy - base * 0.3, base * 0.05, cx, cy, base * 1.25);
      corpo.addColorStop(0, tom(dCor, 1, 78, alfa));
      corpo.addColorStop(0.55, tom(dCor, 1, 52, alfa * 0.55));
      corpo.addColorStop(1, tom(dCor + 20, 1, 30, 0.02));
      c.fillStyle = corpo;
      c.fill();
    }

    // o fio do contorno
    this.contorno(cx, cy, base, this.fase, e.amp, 0);
    c.lineWidth = Math.max(1, L / 420);
    c.strokeStyle = tom(0, 1, 82, 0.75);
    c.stroke();

    // o miolo, que acende com a voz
    const miolo = c.createRadialGradient(cx, cy, 0, cx, cy, base * (0.38 + this.nivel * 0.5));
    miolo.addColorStop(0, tom(0, 0.6, 96, 0.55 + this.nivel * 0.4));
    miolo.addColorStop(1, tom(0, 1, 60, 0));
    c.fillStyle = miolo;
    c.beginPath();
    c.arc(cx, cy, base * (0.38 + this.nivel * 0.5), 0, Math.PI * 2);
    c.fill();

    // satélites: pontinhos em órbita quando ele está explorando ou estudando
    const satelites = Math.round(e.sat_n);
    for (let s = 0; s < satelites; s++) {
      const a = this.fase * (0.9 + s * 0.23) + (s * Math.PI * 2) / Math.max(1, satelites);
      const r = base * (1.42 + 0.08 * Math.sin(this.fase * 1.7 + s));
      const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a) * 0.82;
      const ponto = c.createRadialGradient(x, y, 0, x, y, L * 0.022);
      ponto.addColorStop(0, tom(15, 0.8, 90, 0.95));
      ponto.addColorStop(1, tom(15, 1, 60, 0));
      c.fillStyle = ponto;
      c.beginPath();
      c.arc(x, y, L * 0.022, 0, Math.PI * 2);
      c.fill();
    }
    c.globalCompositeOperation = "source-over";
    requestAnimationFrame((t) => this.quadro(t));
  }
}

// Quando não há som de verdade para medir (voz desligada ou a voz do aparelho), a orbe
// se mexe com um volume inventado, com o ritmo de sílabas de uma fala.
function nivelDeFaz(duracaoMs) {
  const comeco = performance.now();
  const faixas = new Float32Array(FAIXAS);
  return (agora) => {
    const t = (agora - comeco) / 1000;
    if (agora - comeco > duracaoMs) return null;
    const silaba = Math.pow(Math.abs(Math.sin(t * 9.5)), 1.5) * (0.6 + 0.4 * Math.sin(t * 2.3 + 1));
    for (let i = 0; i < FAIXAS; i++) faixas[i] = Math.max(0, silaba * (0.8 - i / FAIXAS) + 0.25 * Math.sin(t * 13 + i));
    return { nivel: 0.25 + 0.5 * silaba, faixas };
  };
}

window.Orbe = Orbe;
window.nivelDeFaz = nivelDeFaz;
window.FAIXAS_DA_ORBE = FAIXAS;
