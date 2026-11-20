// Modo escucha de Liberty: el micrófono queda abierto mientras la pestaña de la oficina esté abierta.
// Cada frase que dices se transcribe (Whisper en CPU, en tu PC) y, si empieza por «Liberty», se le manda.
// Si solo dices «Liberty», la siguiente frase (en los 10 s siguientes) es la orden.
const RATE = 16000;
const WAKE = /^\W*(?:oye\W+|hola\W+)?(liberty|liberti|líberti|libertí|liverty|libert)\b[\s,.:!¿?¡-]*/i;
let ctx, stream, node, src, on = false, opts;
let pre = [], cur = null, silentMs = 0, floor = 0.01, armedUntil = 0, busy = false;

const $ = id => document.getElementById(id);
function setBtn(state) {
  const b = $('btnListen');
  b.dataset.on = on ? '1' : '';
  b.textContent = !on ? '🎙 Escucha: no' : state === 'oyendo' ? '🎙 Te oigo…' : state === 'pensando' ? '🎙 Transcribiendo…' : Date.now() < armedUntil ? '🎙 ¿Sí?' : '🎙 Escuchando';
}

function downsample(buf, rate) {
  if (rate === RATE) return buf.slice();
  const ratio = rate / RATE, out = new Float32Array(Math.floor(buf.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const a = Math.floor(i * ratio), b = Math.min(buf.length, Math.floor((i + 1) * ratio));
    let s = 0; for (let j = a; j < b; j++) s += buf[j];
    out[i] = s / Math.max(1, b - a);
  }
  return out;
}

function onAudio(e) {
  const raw = e.inputBuffer.getChannelData(0);
  const ms = raw.length / ctx.sampleRate * 1000;
  let sum = 0; for (let i = 0; i < raw.length; i++) sum += raw[i] * raw[i];
  const rms = Math.sqrt(sum / raw.length);
  // Liberty hablando (o pensando la respuesta): no se escucha a sí misma
  if (opts.libertyBusy()) { cur = null; pre = []; return; }
  const speech = rms > Math.max(0.015, floor * 3);
  if (!speech && !cur) floor = floor * 0.95 + rms * 0.05;      // ruido de fondo
  const chunk = downsample(raw, ctx.sampleRate);
  if (cur) {
    cur.push(chunk); cur.ms += ms;
    silentMs = speech ? 0 : silentMs + ms;
    if (silentMs > 800 || cur.ms > 15000) finish();
  } else {
    pre.push(chunk); if (pre.length > 4) pre.shift();            // ~300 ms antes de empezar a hablar
    if (speech) { cur = [...pre]; cur.ms = 0; silentMs = 0; pre = []; setBtn('oyendo'); }
  }
}

async function finish() {
  const parts = cur; cur = null;
  if (parts.ms < 350) return setBtn();                          // un golpe, no una frase
  const len = parts.reduce((n, p) => n + p.length, 0), audio = new Float32Array(len);
  let o = 0; for (const p of parts) { audio.set(p, o); o += p.length; }
  if (busy) return; busy = true; setBtn('pensando');
  try {
    const res = await fetch('/api/stt', { method: 'POST', body: audio.buffer, headers: { 'X-Office-Token': opts.token } });
    const d = await res.json();
    if (d.error) throw new Error(d.error);
    handle((d.text || '').trim());
  } catch (err) { opts.toast('Escucha: ' + err.message, 5000); }
  finally { busy = false; setBtn(); }
}

function handle(text) {
  if (!text) return;
  const m = text.match(WAKE);
  let order = null;
  if (m) {
    order = text.slice(m[0].length).trim();
    if (!order) { armedUntil = Date.now() + 10000; opts.toast('Liberty te escucha: dime…'); setTimeout(setBtn, 10100); return; }
  } else if (Date.now() < armedUntil) order = text;
  if (!order) return;                                           // conversación que no va con ella
  armedUntil = 0;
  opts.toast(`🎙 «${order}»`, 4000);
  opts.send(order);
}

async function start() {
  const st = await opts.api('/api/stt/start', {});
  if (st.state === 'error') throw new Error(st.error || 'el transcriptor falló');
  stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  ctx = new AudioContext();
  src = ctx.createMediaStreamSource(stream);
  node = ctx.createScriptProcessor(4096, 1, 1);
  node.onaudioprocess = onAudio;
  src.connect(node); node.connect(ctx.destination);             // (no suena: la salida va vacía)
  on = true; setBtn();
  if (st.state !== 'ready') opts.toast('Cargando el transcriptor la primera vez (unos segundos)…', 5000);
  try { localStorage.setItem('office-listen', '1'); } catch (e) { /* sin almacenamiento */ }
}
function stop() {
  on = false; cur = null; pre = [];
  try { node?.disconnect(); src?.disconnect(); stream?.getTracks().forEach(t => t.stop()); ctx?.close(); } catch (e) { /* ya cerrado */ }
  setBtn();
  try { localStorage.removeItem('office-listen'); } catch (e) { /* sin almacenamiento */ }
}

export function initListen(o) {
  opts = o; setBtn();
  $('btnListen').onclick = async () => {
    if (o.demo) return o.toast('Modo demo: Liberty no escucha');
    if (on) { stop(); return o.toast('Liberty deja de escuchar'); }
    try { await start(); o.toast('Liberty escucha: empieza tus frases con «Liberty…»', 5000); }
    catch (e) { stop(); o.toast('No pude abrir el micrófono: ' + e.message, 6000); }
  };
  // si estaba activa antes de recargar, se reactiva (el navegador recuerda el permiso del micrófono)
  let was = false; try { was = localStorage.getItem('office-listen') === '1'; } catch (e) { /* sin almacenamiento */ }
  if (was && !o.demo) start().catch(() => stop());
}
