// A janela do K.E.R.N.E.L (a mesma no PC e no celular).
// De tempos em tempos pergunta à API pelas mensagens novas e pelo estado, desenha as falas,
// toca a voz dele e passa o volume para a orbe.
"use strict";

const $ = (id) => document.getElementById(id);
const ROTULOS = { iniciativa: "por conta própria", lembranca: "memória", cerebro: "cérebro",
                  pedido: "posso?", aviso: "aviso", conhecimento: "do que estudei", pesquisa: "da internet" };
const DESFECHOS = { executado: "Permitido e feito.", falhou: "Permitido, mas falhou.", negado: "Negado por você.",
                    expirado: "Expirou sem resposta.", aprovado: "Permitido." };
const NOMES = { organizacao: "organização" };

let chave = window.KERNEL_CODIGO || localStorage.getItem("kernel.chave") || "";
let estado = null;
let sessao = null;               // a partida do serviço que esta página acompanha (os números das mensagens são dela)
let ultimoId = 0;
let falarDepoisDe = null;        // mensagens anteriores a esta são histórico: não são faladas
let desligado = false;
let esperandoResposta = false;
let mudo = localStorage.getItem("kernel.mudo") === "1";
let abaAtiva = "registro";
const cartoes = new Map();       // id do pedido -> elemento
const orbe = new Orbe($("orbe"));

// ---------------------------------------------------------------------- API
async function api(caminho, corpo, metodo) {
  const opcoes = { headers: { "X-Kernel-Codigo": chave } };
  if (corpo !== undefined || metodo) {
    opcoes.method = metodo || "POST";
    opcoes.headers["Content-Type"] = "application/json";
    if (corpo !== undefined) opcoes.body = JSON.stringify(corpo);
  }
  const resposta = await fetch(caminho, opcoes);
  if (resposta.status === 401) { pedirPareamento(); throw new Error("sem acesso"); }
  if (!resposta.ok) throw new Error(`${caminho}: ${resposta.status}`);
  return resposta.json();
}

function hora(iso) {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

// ---------------------------------------------------------------------- voz
let contexto = null, analisador = null, amostras = null, espectro = null;
const fila = [];
let falando = false;

function acordarAudio() {
  if (!contexto) {
    const Contexto = window.AudioContext || window.webkitAudioContext;
    if (!Contexto) return;
    contexto = new Contexto();
    analisador = contexto.createAnalyser();
    analisador.fftSize = 512;
    analisador.smoothingTimeConstant = 0.55;
    analisador.connect(contexto.destination);
    amostras = new Uint8Array(analisador.fftSize);
    espectro = new Uint8Array(analisador.frequencyBinCount);
  }
  if (contexto.state === "suspended") contexto.resume();
  pegarAVoz();
}
// o navegador só deixa tocar som depois de um toque ou tecla
for (const evento of ["pointerdown", "keydown", "touchend"]) addEventListener(evento, acordarAudio, { passive: true });

// Com duas janelas abertas no mesmo navegador, só uma fala: aquela em que você mexeu por último. Ela toma
// a trava "kernel-voz" e a outra fica muda até você mexer nela de novo. (No celular, por http, o navegador
// não oferece travas; lá cada aparelho fala por si.)
let donaDaVoz = !("locks" in navigator);
function pegarAVoz() {
  if (donaDaVoz || !("locks" in navigator)) return;
  donaDaVoz = true;
  navigator.locks.request("kernel-voz", { steal: true }, () => new Promise(() => {}))
    .catch(() => { donaDaVoz = false; });  // outra janela tomou a trava
}

function nivelDaVoz() {
  // volume: raiz da média dos quadrados da onda; faixas: o espectro até uns 5 kHz
  analisador.getByteTimeDomainData(amostras);
  let soma = 0;
  for (const a of amostras) soma += ((a - 128) / 128) ** 2;
  analisador.getByteFrequencyData(espectro);
  const n = window.FAIXAS_DA_ORBE, faixas = new Float32Array(n);
  const ate = Math.floor(espectro.length * 5200 / (contexto.sampleRate / 2));
  for (let i = 0; i < n; i++) {
    const a = Math.floor((i / n) ** 1.6 * ate), b = Math.max(a + 1, Math.floor(((i + 1) / n) ** 1.6 * ate));
    let maior = 0;
    for (let k = a; k < b; k++) maior = Math.max(maior, espectro[k]);
    faixas[i] = maior / 255;
  }
  return { nivel: Math.min(1, Math.sqrt(soma / amostras.length) * 3.2), faixas };
}

function falar(mensagem) {
  fila.push(mensagem);
  if (!falando) proximaFala();
}

function fimDaFala() {
  orbe.fonte = null;
  falando = false;
  proximaFala();
}

async function proximaFala() {
  const mensagem = fila.shift();
  if (!mensagem) { atualizarOrbe(); return; }
  falando = true;
  atualizarOrbe();
  const fazDeConta = () => {  // sem som: a orbe se mexe pelo tempo que a frase levaria
    const ms = Math.min(9000, 500 + mensagem.texto.length * 55);
    orbe.fonte = window.nivelDeFaz(ms);
    setTimeout(fimDaFala, ms);
  };
  if (mudo || !donaDaVoz || !estado || !estado.voz.ligada) return fazDeConta();
  if (estado.voz.motor === "aparelho" && "speechSynthesis" in window) {
    const fala = new SpeechSynthesisUtterance(mensagem.texto.slice(0, 400));
    fala.lang = "pt-BR";
    fala.pitch = 0.8;
    fala.onend = fala.onerror = fimDaFala;
    orbe.fonte = window.nivelDeFaz(60000);
    speechSynthesis.speak(fala);
    return;
  }
  try {
    if (!contexto || contexto.state !== "running") return fazDeConta();
    // sem guardar no navegador e com a marca da partida: o número 7 de hoje não é o 7 de antes do reinício
    const resposta = await fetch(`/api/voz/${mensagem.id}?s=${sessao || ""}`,
                                 { headers: { "X-Kernel-Codigo": chave }, cache: "no-store" });
    if (resposta.status !== 200) return fazDeConta();
    const som = await contexto.decodeAudioData(await resposta.arrayBuffer());
    const fonte = contexto.createBufferSource();
    fonte.buffer = som;
    fonte.connect(analisador);
    fonte.onended = fimDaFala;
    orbe.fonte = nivelDaVoz;
    fonte.start();
  } catch (erro) {
    fazDeConta();
  }
}

function atualizarOrbe() {
  let nome = "ocioso";
  if (desligado || !estado) nome = "desligado";
  else if (falando) nome = "falando";
  else if (estado.atividade === "pesquisando") nome = "pesquisando";   // foi à internet (por conta própria ou a seu pedido)
  else if (esperandoResposta) nome = "pensando";
  else if (estado.modo_seguro) nome = "alerta";
  else if (estado.atividade === "pausado") nome = "pausado";
  else if (estado.atividade === "explorando") nome = "explorando";
  else if (estado.atividade === "estudando") nome = "estudando";
  orbe.estado(nome);
}

// -------------------------------------------------------------------- falas
function desenharFala(m) {
  const caixa = document.createElement("div");
  caixa.className = m.autor === "voce" ? "fala voce" : `fala kernel ${m.classe}`;
  if (m.antiga) caixa.classList.add("antiga");
  if (m.autor !== "voce" && ROTULOS[m.classe]) {
    const rotulo = document.createElement("span");
    rotulo.className = "rotulo";
    rotulo.textContent = ROTULOS[m.classe];
    caixa.append(rotulo);
  }
  caixa.append(document.createTextNode(m.texto));
  caixa.title = hora(m.ts);
  if (m.fonte) {
    // a fonte de uma resposta da internet vira link; só http(s), e sempre numa aba nova do seu navegador
    const comLink = typeof m.link === "string" && /^https?:\/\//i.test(m.link);
    const fonte = document.createElement(comLink ? "a" : "span");
    fonte.className = "fonte";
    fonte.textContent = m.fonte;
    if (comLink) {
      fonte.href = m.link;
      fonte.target = "_blank";
      fonte.rel = "noopener noreferrer";
    }
    caixa.append(fonte);
  }
  if (m.classe === "pedido" && m.pedido) {
    const acoes = document.createElement("div");
    acoes.className = "acoes";
    for (const [texto, classe, aprovar] of [["Permitir", "permitir", true], ["Negar", "negar", false]]) {
      const botao = document.createElement("button");
      botao.className = classe;
      botao.textContent = texto;
      botao.onclick = async () => {
        acoes.querySelectorAll("button").forEach((b) => (b.disabled = true));
        await api(`/api/pedido/${m.pedido}`, { aprovar });
        atualizar();
      };
      acoes.append(botao);
    }
    caixa.append(acoes);
    cartoes.set(m.pedido, caixa);
  }
  return caixa;
}

function marcarPedidos(estados) {
  for (const [id, caixa] of cartoes) {
    const situacao = estados[id];
    if (!situacao || situacao === "pendente" || caixa.classList.contains("resolvido")) continue;
    caixa.classList.add("resolvido");
    caixa.querySelector(".acoes")?.remove();
    const desfecho = document.createElement("div");
    desfecho.className = "desfecho";
    desfecho.textContent = DESFECHOS[situacao] || situacao;
    caixa.append(desfecho);
  }
}

function receberMensagens(novas) {
  const lista = $("falas");
  novas = novas.filter((m) => m.id > ultimoId);  // nunca desenha (nem fala) a mesma mensagem duas vezes
  if (!novas.length) return;
  $("vazio")?.remove();
  const noFim = lista.scrollHeight - lista.scrollTop - lista.clientHeight < 120;
  for (const m of novas) {
    lista.append(desenharFala(m));
    ultimoId = Math.max(ultimoId, m.id);
    if (m.autor === "kernel") {
      esperandoResposta = false;
      if (falarDepoisDe !== null && m.id > falarDepoisDe) falar(m);
    }
  }
  while (lista.children.length > 80) lista.firstElementChild.remove();
  if (noFim || novas.some((m) => m.autor === "voce")) lista.scrollTop = lista.scrollHeight;
}

// ------------------------------------------------------------------- estado
const SITUACOES = {
  explorando: (e) => `explorando${e.detalhe ? " · " + e.detalhe : ""}`,
  pesquisando: (e) => `pesquisando na internet${e.detalhe ? " · " + e.detalhe : ""}`,
  estudando: (e) => e.detalhe || "estudando",
  pausado: () => "parado a seu pedido",
  ocioso: () => "",
};

function desenharEstado(e) {
  estado = e;
  document.title = e.nome;
  let situacao = (SITUACOES[e.atividade] || SITUACOES.ocioso)(e);
  if (e.modo_seguro) situacao = "modo seguro";
  if (esperandoResposta && e.atividade !== "pesquisando") situacao = "pensando";
  $("situacao").textContent = situacao;
  $("pausa").classList.toggle("pausado", e.pausado);
  $("pausa").title = e.pausado ? "Continuar a autonomia" : "Parar a autonomia";
  atualizarOrbe();
  marcarPedidos(e.pedidos);
  if (!$("falas").children.length) {
    const vazio = document.createElement("div");
    vazio.className = "vazio";
    vazio.id = "vazio";
    vazio.textContent = `Olá, ${e.usuario}.`;
    $("falas").append(vazio);
  }
  if (!$("gaveta").hidden) desenharGaveta();
}

function desenharGaveta() {
  const e = estado;
  if (!e) return;
  $("modo-seguro").hidden = !e.modo_seguro;
  $("modo-seguro").textContent = e.modo_seguro
    ? `Modo seguro: ${e.motivo_modo_seguro}. Mãos e autonomia desligadas até você rodar "python -m kernel selar".` : "";
  const x = e.exploracao, n = x.numeros;
  $("autonomia-texto").textContent = e.pausado ? 'Parado a seu pedido. Diga "pode continuar" ou toque no botão ▶.'
    : !x.ligada ? "A exploração está desligada na configuração."
    : `Explorando sozinho (ritmo ${x.ritmo}${x.ler_arquivos ? "" : ", só nomes"}): ${n.pastas_visitadas} de ${n.pastas} pastas, `
      + `${n.arquivos} arquivos vistos, ${n.arquivos_lidos} lidos.`;
  $("pastas").replaceChildren(...x.pastas.map((p) => Object.assign(document.createElement("li"), { textContent: p })));
  $("orgao-cerebro").textContent = e.cerebro.descricao;
  $("orgao-saber").textContent = e.conhecimento ? `${e.conhecimento} artigos estudados` : 'nada ainda (diga "estuda a wikipédia")';
  const m = e.memoria, total = m.total || 0;
  const partes = Object.entries(m).filter(([tipo]) => tipo !== "total").map(([tipo, q]) => `${q} ${tipo}`);
  $("orgao-memoria").textContent = `${total} ${total === 1 ? "lembrança" : "lembranças"}` + (partes.length ? ` (${partes.join(", ")})` : "");
  $("orgao-ouvidos").textContent = e.ouvidos.descricao;
  const i = e.internet;
  $("orgao-internet").textContent = !i.ligada ? "desligada (kernel.toml, seção [internet])"
    : `${i.sozinho ? "pesquisa sozinho e a seu pedido" : "só a seu pedido"} · ${i.pesquisados} assuntos, ${i.paginas} páginas lidas`
      + (i.na_fila ? ` · ${i.na_fila} na fila` : "") + (i.sozinho ? ` · ${i.na_ultima_hora} de ${i.teto} pedidos nesta hora` : "");
  $("versao").textContent = `versão ${e.versao} · acordado desde ${hora(e.desde)}`;

  const caixa = $("impulsos");
  caixa.replaceChildren();
  for (const [nome, valor] of Object.entries(e.impulsos)) {
    const bloco = document.createElement("div");
    bloco.className = "impulso";
    const linha = document.createElement("div");
    linha.className = "linha";
    linha.append(Object.assign(document.createElement("span"), { textContent: NOMES[nome] || nome }),
                 Object.assign(document.createElement("span"), { className: "valor", textContent: valor.toFixed(2) }));
    const barra = document.createElement("div");
    barra.className = "barra" + (valor >= e.limiar_impulso ? " cheia" : "");
    const cheio = document.createElement("i");
    cheio.style.width = `${Math.round(valor * 100)}%`;
    const limiar = document.createElement("b");
    limiar.style.left = `${e.limiar_impulso * 100}%`;
    barra.append(cheio, limiar);
    bloco.append(linha, barra);
    caixa.append(bloco);
  }
}

async function desenharRegistro() {
  const entradas = await api("/api/registro?n=80");
  $("registro").replaceChildren(...entradas.reverse().map(({ ts, tipo, ...resto }) => {
    const item = document.createElement("li");
    const detalhe = JSON.stringify(resto);
    item.title = detalhe;
    item.append(Object.assign(document.createElement("time"), { textContent: ts.slice(11) }),
                Object.assign(document.createElement("span"), { className: "tipo", textContent: tipo }),
                document.createTextNode(detalhe.length > 200 ? detalhe.slice(0, 200) + "…" : detalhe));
    return item;
  }));
}

async function desenharDiario() {
  const diario = await api("/api/diario");
  $("diario").textContent = diario.texto || "Ainda não há diário. Ele escreve sozinho no fim do dia.";
}

async function desenharCelular() {
  if (!window.KERNEL_LOCAL) return;
  $("secao-celular").hidden = false;
  const c = await api("/api/celular");
  $("gerar-codigo").hidden = !c.ligado;
  $("celular-texto").textContent = !c.ligado
    ? "Desligado. Para falar com ele pelo celular, ponha ligado = true em [celular] no kernel.toml e reinicie."
    : c.enderecos.length ? `No celular, na mesma rede Wi-Fi, abra: ${c.enderecos.join("  ou  ")}`
    : "Este PC não parece estar numa rede local agora.";
  $("aparelhos").replaceChildren(...c.aparelhos.map((a) => {
    const item = document.createElement("li");
    const esquecer = Object.assign(document.createElement("button"), { textContent: "esquecer" });
    esquecer.onclick = async () => { await api(`/api/celular/${a.id}`, undefined, "DELETE"); desenharCelular(); };
    item.append(document.createTextNode(`${a.nome} · desde ${a.desde.slice(0, 10)}`), esquecer);
    return item;
  }));
}

// --------------------------------------------------------------------- laço
let atualizando = false, deNovo = false, falhas = 0;

async function atualizar() {
  if (desligado) return;
  // Uma consulta por vez. Duas ao mesmo tempo perguntavam "o que há depois da mensagem N?" com o mesmo N,
  // recebiam as mesmas mensagens e cada uma era desenhada e falada em dobro.
  if (atualizando) { deNovo = true; return; }
  atualizando = true;
  try {
    const [novoEstado, novas] = await Promise.all([api("/api/estado"), api(`/api/mensagens?desde=${ultimoId}`)]);
    falhas = 0;
    if (sessao !== null && novoEstado.sessao !== sessao) {  // o serviço reiniciou: os números recomeçaram do 1
      location.reload();
      return;
    }
    sessao = novoEstado.sessao;
    if (falarDepoisDe === null) {  // primeira leitura: o que já estava lá é histórico
      novas.forEach((m) => (m.antiga = true));
      falarDepoisDe = novas.length ? novas[novas.length - 1].id : novoEstado.ultimo_id;
    }
    receberMensagens(novas);
    desenharEstado(novoEstado);
  } catch (erro) {
    // um tropeço isolado não apaga o que a página já sabe (apagar desligava a voz e a orbe por nada)
    if (++falhas >= 3) {
      if ($("parear").hidden) $("situacao").textContent = "sem resposta do serviço";
      estado = null;
      atualizarOrbe();
    }
  } finally {
    atualizando = false;
    if (deNovo) { deNovo = false; atualizar(); }
  }
}

// ------------------------------------------------------------------ entrada
let enviando = false;

$("entrada").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  acordarAudio();
  const campo = $("texto");
  const texto = campo.value.trim();
  if (!texto || enviando) return;  // um envio por vez: um Enter repetido não manda a mesma fala duas vezes
  enviando = true;
  campo.value = "";
  campo.style.height = "auto";
  esperandoResposta = true;
  atualizarOrbe();
  try {
    await api("/api/mensagem", { texto });
  } catch (erro) {
    if (!campo.value) campo.value = texto;
  }
  enviando = false;
  esperandoResposta = false;
  atualizar();
});

$("texto").addEventListener("keydown", (evento) => {
  if (evento.key === "Enter" && !evento.shiftKey && !evento.isComposing) {
    evento.preventDefault();
    $("entrada").requestSubmit();
  }
});

$("texto").addEventListener("input", (evento) => {
  evento.target.style.height = "auto";
  evento.target.style.height = `${evento.target.scrollHeight}px`;
});

// ------------------------------------------------------------------- botões
function pintarSom() {
  $("som").classList.toggle("desligado", mudo);
  $("som").title = mudo ? "Voz desligada" : "Voz ligada";
}
pintarSom();

$("som").addEventListener("click", () => {
  mudo = !mudo;
  localStorage.setItem("kernel.mudo", mudo ? "1" : "0");
  pintarSom();
});

$("pausa").addEventListener("click", async () => {
  if (!estado) return;
  await api("/api/autonomia", { pausar: !estado.pausado });
  atualizar();
});

$("menu").addEventListener("click", () => {
  $("gaveta").hidden = false;
  desenharGaveta();
  desenharRegistro().catch(() => {});
  desenharCelular().catch(() => {});
});
$("fechar").addEventListener("click", () => ($("gaveta").hidden = true));
addEventListener("keydown", (evento) => { if (evento.key === "Escape") $("gaveta").hidden = true; });

for (const aba of document.querySelectorAll(".aba")) {
  aba.addEventListener("click", () => {
    abaAtiva = aba.dataset.aba;
    document.querySelectorAll(".aba").forEach((a) => a.classList.toggle("ativa", a === aba));
    $("registro").hidden = abaAtiva !== "registro";
    $("aba-diario").hidden = abaAtiva !== "diario";
    (abaAtiva === "registro" ? desenharRegistro() : desenharDiario()).catch(() => {});
  });
}

$("escrever-diario").addEventListener("click", async () => {
  $("diario").textContent = (await api("/api/diario", {})).texto;
});

$("gerar-codigo").addEventListener("click", async () => {
  const resposta = await api("/api/celular/codigo", {});
  const caixa = $("codigo-de-pareamento");
  caixa.hidden = false;
  caixa.textContent = resposta.codigo;
  caixa.append(Object.assign(document.createElement("small"),
    { textContent: `Digite este código no celular. Vale ${resposta.minutos} minutos e serve para um aparelho.` }));
});

// desligar pede dois toques: o primeiro arma, o segundo (em até 4 s) desliga
$("desligar").addEventListener("click", async () => {
  const botao = $("desligar");
  if (!botao.classList.contains("armado")) {
    botao.classList.add("armado");
    botao.textContent = "Toque de novo para desligar";
    setTimeout(() => { botao.classList.remove("armado"); botao.textContent = "Desligar o K.E.R.N.E.L"; }, 4000);
    return;
  }
  desligado = true;
  try { await api("/api/desligar", {}); } catch (erro) { /* ele pode cair antes de responder */ }
  atualizarOrbe();
  $("gaveta").hidden = true;
  $("cortina").hidden = false;
});

// --------------------------------------------------------------- pareamento
function pedirPareamento() {
  if (window.KERNEL_LOCAL) return;  // no PC a página já vem com o código; 401 aqui é serviço reiniciado
  localStorage.removeItem("kernel.chave");
  chave = "";
  $("parear").hidden = false;
}

$("form-parear").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  $("erro-parear").textContent = "";
  const resposta = await fetch("/api/parear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ codigo: $("codigo").value.trim(), nome: $("nome-aparelho").value.trim() || "celular" }),
  });
  if (!resposta.ok) {
    $("erro-parear").textContent = "Código errado ou vencido. Gere outro no PC.";
    return;
  }
  chave = (await resposta.json()).chave;
  localStorage.setItem("kernel.chave", chave);
  $("parear").hidden = true;
  acordarAudio();
  atualizar();
});

// no PC, se o serviço reiniciou, a página antiga tem um código velho: recarrega para pegar o novo
let falhasSeguidas = 0;
setInterval(async () => {
  if (!window.KERNEL_LOCAL || desligado) return;
  try {
    const r = await fetch("/api/estado", { headers: { "X-Kernel-Codigo": chave } });
    falhasSeguidas = r.status === 401 ? falhasSeguidas + 1 : 0;
    if (falhasSeguidas >= 2) location.reload();
  } catch (erro) { /* serviço fora do ar: a tela já avisa */ }
}, 5000);

if (!chave && !window.KERNEL_LOCAL) pedirPareamento();
atualizar();
setInterval(atualizar, 1500);
