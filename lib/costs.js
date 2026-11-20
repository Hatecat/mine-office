// Ventana «Gastos»: lo que ha costado cada agente (estimación a precio de API).
const PALETTE = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#0ca30c', '#9085e9', '#e66767'];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const $ = id => document.getElementById(id);

export function money(v) {
  if (v == null) return '—';
  if (v === 0) return '$0';
  if (v < 0.01) return '<$0.01';
  return '$' + (v < 100 ? v.toFixed(2) : Math.round(v).toLocaleString('es-ES'));
}
const ktok = n => n >= 1e6 ? (n / 1e6).toFixed(1) + ' M' : n >= 1e3 ? Math.round(n / 1e3) + ' k' : String(n);
const fdate = (t, withTime = true) => new Date(t * 1000).toLocaleString('es-ES', withTime ? { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' } : { day: 'numeric', month: 'short' });
const fdur = s => s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;

let data = null, fetchedAt = 0, ctx = null;

export async function loadUsage(force = false) {
  if (!force && data && performance.now() - fetchedAt < 30000) return data;
  data = ctx.DEMO ? demo() : await ctx.api('/api/usage');
  fetchedAt = performance.now();
  return data;
}
export function memberCost(memberId) {
  const a = data?.agents.find(x => x.member === memberId);
  return a ? a : null;
}

// color fijo por agente según su orden en la lista (miembros primero); más de 8 → «Resto»
function colorize(agents) {
  const withSpend = agents.filter(a => a.month > 0 || a.kind === 'member');
  const map = new Map();
  withSpend.forEach((a, i) => map.set(a.key, i < 7 || withSpend.length <= 8 ? PALETTE[i] : null));
  return map;
}

function render() {
  const d = data, body = $('costBody');
  if (!d) return;
  const sum = k => d.agents.reduce((n, a) => n + (a[k] || 0), 0);
  const colors = colorize(d.agents);
  const series = d.agents.filter(a => colors.has(a.key));
  const restKeys = new Set(series.filter(a => !colors.get(a.key)).map(a => a.key));
  const shown = series.filter(a => colors.get(a.key));
  if (restKeys.size) shown.push({ key: '__rest', name: 'Resto' }), colors.set('__rest', '#8a90a0');

  const kpi = (label, v, sub) => `<div class="kpi"><div class="kl">${label}</div><div class="kv">${money(v)}</div>${sub ? `<div class="ks">${sub}</div>` : ''}</div>`;
  const tokAll = sum('tokIn') + sum('tokOut') + sum('tokCache');
  let html = `<p class="cnote">Precio que costaría por la API (tokens × tarifa de cada modelo). Con el plan Pro no se cobra aparte: sirve para comparar agentes y ver quién gasta más.${d.ready ? '' : ' <b>Leyendo transcripciones…</b>'}</p>
  <div class="kpis">${kpi('Hoy', sum('today'))}${kpi('Últimos 7 días', sum('week'))}${kpi('Últimos 30 días', sum('month'))}${kpi('Total registrado', sum('total'), ktok(tokAll) + ' tokens')}</div>`;

  // barras apiladas por día
  const days = d.days, max = Math.max(...days.map(x => Object.values(x.by).reduce((n, v) => n + v, 0)), 0);
  const W = 720, H = 170, padL = 46, padB = 22, bw = (W - padL) / days.length;
  const nice = max <= 0 ? 1 : Math.pow(10, Math.floor(Math.log10(max))) * ([1, 2, 5, 10].find(m => m * Math.pow(10, Math.floor(Math.log10(max))) >= max));
  const y = v => H - padB - (v / nice) * (H - padB - 8);
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Gasto diario de los últimos ${days.length} días">`;
  for (const f of [0, 0.5, 1]) svg += `<line x1="${padL}" x2="${W}" y1="${y(nice * f)}" y2="${y(nice * f)}" class="grid"/><text x="${padL - 6}" y="${y(nice * f) + 5}" class="ax" text-anchor="end">${money(nice * f)}</text>`;
  days.forEach((day, i) => {
    const x = padL + i * bw + 2, w = Math.max(2, bw - 4);
    let acc = 0; const parts = [];
    for (const a of shown) {
      const v = a.key === '__rest' ? [...restKeys].reduce((n, k) => n + (day.by[k] || 0), 0) : (day.by[a.key] || 0);
      if (v <= 0) continue;
      const y0 = y(acc), y1 = y(acc + v); acc += v;
      const h = Math.max(1, y0 - y1 - 2);           // 2px de separación entre tramos
      parts.push(`<rect x="${x}" y="${y0 - h}" width="${w}" height="${h}" fill="${colors.get(a.key)}"/>`);
    }
    const tip = [`${fdate(new Date(day.date + 'T12:00').getTime() / 1000, false)}: ${money(acc)}`,
      ...shown.map(a => [a.name, a.key === '__rest' ? [...restKeys].reduce((n, k) => n + (day.by[k] || 0), 0) : (day.by[a.key] || 0)]).filter(p => p[1] > 0).map(p => `${p[0]}: ${money(p[1])}`)].join('\n');
    svg += `<g class="bar" data-tip="${esc(tip)}"><rect x="${padL + i * bw}" y="0" width="${bw}" height="${H - padB}" class="hit"/>${parts.join('')}</g>`;
    if (i % 5 === 0 || i === days.length - 1) svg += `<text x="${x + w / 2}" y="${H - 5}" class="ax" text-anchor="middle">${i === days.length - 1 ? 'hoy' : day.date.slice(8) + '/' + day.date.slice(5, 7)}</text>`;
  });
  svg += '</svg>';
  const legend = shown.map(a => `<span><i style="background:${colors.get(a.key)}"></i>${esc(a.name)}</span>`).join('');
  html += `<h3>Gasto por día (últimos ${days.length} días)</h3><div class="legend">${legend}</div><div class="chartwrap">${svg}<div class="tip" id="costTip"></div></div>`;

  // tabla por agente
  const rows = [...d.agents].sort((a, b) => (b.kind === 'member') - (a.kind === 'member') || b.total - a.total);
  html += `<h3>Por agente</h3><div class="tbl"><table><thead><tr><th>Agente</th><th>Modelo</th><th>Hoy</th><th>7 días</th><th>Total</th><th>Tokens</th><th>Respuestas</th><th>Última vez</th></tr></thead><tbody>`;
  for (const a of rows) {
    const c = colors.get(a.key) || (restKeys.has(a.key) ? '#8a90a0' : 'transparent');
    const models = Object.entries(a.models || {}).sort((x, y) => y[1] - x[1]).map(([m]) => m.replace(/^claude-/, '').replace(/^opencode\//, '')).slice(0, 2).join(', ') || (a.model || '').replace(/^claude-/, '') || '—';
    html += `<tr><td><i class="sw2" style="background:${c}"></i>${esc(a.name)}${a.team ? ` <span class="mut">· ${esc(a.team)}</span>` : ''}</td><td class="mut">${esc(models)}</td><td>${money(a.today)}</td><td>${money(a.week)}</td><td><b>${money(a.total)}</b></td><td class="mut">${ktok(a.tokIn + a.tokOut + a.tokCache)}</td><td class="mut">${a.msgs}</td><td class="mut">${a.last ? fdate(a.last) : '—'}</td></tr>`;
  }
  html += '</tbody></table></div>';

  // órdenes del chat
  html += `<h3>Órdenes dadas desde la oficina</h3>`;
  if (!d.runs.length) html += '<p class="mut">Todavía no hay órdenes registradas. Cada orden que mandes desde el chat aparecerá aquí con lo que costó.</p>';
  else {
    html += '<div class="tbl runs"><table><thead><tr><th>Cuándo</th><th>Agente</th><th>Orden</th><th>Duración</th><th>Coste</th></tr></thead><tbody>';
    for (const r of d.runs) {
      const st = r.error ? `<span class="bad">✖ ${esc(r.error.slice(0, 60))}</span>` : r.denials?.length ? `<span class="warnc">! pidió permiso</span>` : '';
      html += `<tr><td class="mut">${fdate(r.t)}</td><td>${esc(r.name)}</td><td>${esc(r.prompt)}${st ? '<br>' + st : ''}</td><td class="mut">${fdur(r.t - r.start)}</td><td>${money(r.reported ?? r.cost)}</td></tr>`;
    }
    html += '</tbody></table></div>';
  }
  body.innerHTML = html;

  const tipEl = $('costTip'), wrap = body.querySelector('.chartwrap');
  body.querySelectorAll('.bar').forEach(g => {
    g.addEventListener('pointerenter', () => { tipEl.textContent = g.dataset.tip; tipEl.style.display = 'block'; g.classList.add('on'); });
    g.addEventListener('pointerleave', () => { tipEl.style.display = 'none'; g.classList.remove('on'); });
    g.addEventListener('pointermove', e => {
      const r = wrap.getBoundingClientRect();
      const x = Math.min(e.clientX - r.left + 14, r.width - tipEl.offsetWidth - 4);
      tipEl.style.left = x + 'px'; tipEl.style.top = Math.max(0, e.clientY - r.top - tipEl.offsetHeight - 10) + 'px';
    });
  });
}

export function initCosts(c) {
  ctx = c;
  const dlg = $('costs');
  $('btnCosts').onclick = async () => {
    $('costBody').innerHTML = '<p class="mut">Calculando…</p>';
    dlg.showModal();
    try { await loadUsage(true); render(); } catch (e) { $('costBody').innerHTML = `<p class="bad">${esc(e.message)}</p>`; }
  };
  $('costRefresh').onclick = async () => { try { await loadUsage(true); render(); } catch (e) { ctx.toast(e.message); } };
}

function demo() {
  const now = Date.now() / 1000, today = new Date(); today.setHours(0, 0, 0, 0);
  const keys = ['m:rocio', 'm:bruno', 'm:nube', 'm:iker', 'cc'];
  const days = Array.from({ length: 30 }, (_, i) => {
    const dt = new Date(today.getTime() - (29 - i) * 86400000);
    const by = {}; keys.forEach((k, j) => { const v = Math.max(0, Math.sin(i * 0.7 + j * 1.3) + 0.4) * [0.8, 0.05, 0, 2.4, 6][j]; if (v > 0) by[k] = v; });
    return { date: dt.toISOString().slice(0, 10), by };
  });
  const tot = k => days.reduce((n, d) => n + (d.by[k] || 0), 0);
  const ag = (key, name, model, extra) => ({ key, name, model, models: { [model]: tot(key) }, today: days[29].by[key] || 0, week: days.slice(23).reduce((n, d) => n + (d.by[key] || 0), 0), month: tot(key), total: tot(key), tokIn: 2e6, tokOut: 1e5, tokCache: 8e6, msgs: 120, last: now - 600, ...extra });
  return {
    ready: true, days, agents: [
      ag('m:rocio', 'Rocío', 'claude-sonnet-5-5', { kind: 'member', member: 'rocio', team: 'Equipo Alfa' }),
      ag('m:bruno', 'Bruno', 'claude-haiku-5-5', { kind: 'member', member: 'bruno', team: 'Equipo Alfa' }),
      ag('m:nube', 'Nube', 'opencode/big-pickle', { kind: 'member', member: 'nube', team: 'Equipo Alfa' }),
      ag('m:iker', 'Iker', 'claude-opus-5-5', { kind: 'member', member: 'iker', team: 'Equipo Beta' }),
      ag('cc', 'Otras sesiones de Claude Code', 'claude-opus-5-5', { kind: 'other' }),
    ],
    runs: [{ t: now - 900, start: now - 1000, name: 'Rocío', prompt: 'Revisa los tests de la API y arregla el que falla', cost: 0.42 },
           { t: now - 4000, start: now - 4030, name: 'Bruno', prompt: 'Lista los TODO del proyecto', cost: 0.003, denials: ['Bash: rm -rf build'] }],
  };
}
