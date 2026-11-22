// 마켓 보드 — 정적 사이트 (GitHub Pages)
// 주소 형식: #<tab>/<date>   예) #us/2026-11-13, #kr, #etf
const TABS = { us: { flag: '🇺🇸', name: '미국' }, kr: { flag: '🇰🇷', name: '한국' }, jp: { flag: '🇯🇵', name: '일본' }, tw: { flag: '🇹🇼', name: '대만' }, etf: { flag: '📊', name: 'ETF' } };
const WD = ['일', '월', '화', '수', '목', '금', '토'];
const FG_KO = { 'extreme fear': '극단적 공포', fear: '공포', neutral: '중립', greed: '탐욕', 'extreme greed': '극단적 탐욕' };
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safe = (t) => t.replace(/[^A-Za-z0-9]/g, '_');

let INDEX = null;
const state = { tab: 'us', date: null, lev: true };
let renderSeq = 0;
const jcache = new Map();
const panels = new Map(); // 패널 id → { items, opts, chart }
let pageCharts = [];

// ------------------------------------------------------------ 공통 유틸
async function getJSON(path) {
  if (jcache.has(path)) return jcache.get(path);
  const r = await fetch(`${path}?v=${encodeURIComponent(INDEX?.updated || Date.now())}`, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  const j = await r.json();
  jcache.set(path, j);
  return j;
}
const fmtDate = (d) => { const [y, m, dd] = d.split('-'); return `${y}.${m}.${dd}(${WD[new Date(d + 'T00:00:00').getDay()]})`; };
const fp = (v, d = 2) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(d)}%`);
const fpp = (v, d = 1) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(d)}%p`);
const fmetric = (it, m) => (m === 'score' ? fpp(it.score) : fp(it[m]));
const cls = (v) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');
const fnum = (v, d) => (v == null ? '–' : v.toLocaleString('ko-KR', { minimumFractionDigits: d ?? (Math.abs(v) >= 1000 ? 0 : 2), maximumFractionDigits: d ?? (Math.abs(v) >= 1000 ? 0 : 2) }));
function fcap(v, mk = 'us') {
  if (mk === 'us') return v >= 1e12 ? `$${(v / 1e12).toFixed(2)}T` : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${Math.round(v / 1e6)}M`;
  const cur = mk === 'jp' ? '엔' : mk === 'tw' ? '대만달러' : '원';
  return v >= 1e12 ? `${(v / 1e12).toFixed(1)}조${cur}` : `${Math.round(v / 1e8).toLocaleString()}억${cur}`;
}
const code = (t) => t.replace(/\.(T|KS|KQ|TW|TWO)$/, '');
const rgba = (hex, a) => { const h = hex.replace('#', ''); const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h; const n = parseInt(f.slice(0, 6), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; };
function theme() {
  const c = getComputedStyle(document.documentElement);
  const g = (k) => c.getPropertyValue(k).trim();
  return { up: g('--up'), down: g('--down'), muted: g('--muted'), line: g('--line'), accent: g('--accent'), fg: g('--fg') };
}

// ------------------------------------------------------------ 차트 라이브러리
const LWC_SRC = [
  'vendor/lightweight-charts.standalone.production.js',
  'https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js',
  'https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js',
];
let lwcPromise = null;
function loadLWC() {
  if (window.LightweightCharts) return Promise.resolve(true);
  if (lwcPromise) return lwcPromise;
  lwcPromise = (async () => {
    for (const src of LWC_SRC) {
      const ok = await new Promise((res) => { const s = document.createElement('script'); s.src = src; s.onload = () => res(!!window.LightweightCharts); s.onerror = () => { s.remove(); res(false); }; document.head.appendChild(s); });
      if (ok) return true;
    }
    lwcPromise = null;
    return false;
  })();
  return lwcPromise;
}
const fmtT = (t) => {
  let y, m, d;
  if (typeof t === 'string') [y, m, d] = t.split('-').map(Number);
  else if (typeof t === 'number') { const x = new Date(t * 1000); y = x.getUTCFullYear(); m = x.getUTCMonth() + 1; d = x.getUTCDate(); }
  else ({ year: y, month: m, day: d } = t);
  return `${String(y).slice(2)}.${String(m).padStart(2, '0')}.${String(d).padStart(2, '0')}`;
};
function makeChart(el, extra = {}) {
  const th = theme();
  const c = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { background: { color: 'transparent' }, textColor: th.muted, fontSize: 11 },
    grid: { vertLines: { visible: false }, horzLines: { color: th.line } },
    rightPriceScale: { borderVisible: false },
    leftPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false },
    localization: { locale: 'ko-KR', timeFormatter: fmtT },
    crosshair: { mode: 0 },
    ...extra,
  });
  pageCharts.push(c);
  return c;
}
function dropChart(c) { if (!c) return; try { c.remove(); } catch {} pageCharts = pageCharts.filter((x) => x !== c); }
function destroyAll() { pageCharts.forEach((c) => { try { c.remove(); } catch {} }); pageCharts = []; panels.clear(); }

function setRange(chart, data, months) {
  if (!data.length) return;
  const last = data[data.length - 1][0];
  if (!months) return chart.timeScale().fitContent();
  const from = new Date(last + 'T00:00:00'); from.setMonth(from.getMonth() - months);
  const f = from.toISOString().slice(0, 10);
  if (f <= data[0][0]) return chart.timeScale().fitContent();
  chart.timeScale().setVisibleRange({ from: f, to: last });
}
const RANGES = { '3M': 3, '6M': 6, '1Y': 12, '3Y': 36, '5Y': 60, '10Y': 120, '전체': 0 };
function bindRanges(box, chart, data, list, def) {
  const span = data.length ? (new Date(data.at(-1)[0]) - new Date(data[0][0])) / 2.6e9 : 0; // 개월 수
  const keys = list.filter((k) => RANGES[k] === 0 || RANGES[k] <= span * 1.05 + 1);
  box.innerHTML = keys.map((k) => `<button data-k="${k}" class="${k === def ? 'on' : ''}">${k}</button>`).join('');
  box.onclick = (e) => {
    const b = e.target.closest('button'); if (!b) return;
    box.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
    setRange(chart, data, RANGES[b.dataset.k]);
  };
  setRange(chart, data, RANGES[keys.includes(def) ? def : keys.at(-1)]);
}


// ------------------------------------------------------------ 마우스 오버 수치 표시
const tkey = (t) => (typeof t === 'string' ? t : typeof t === 'number' ? new Date(t * 1000).toISOString().slice(0, 10)
  : `${t.year}-${String(t.month).padStart(2, '0')}-${String(t.day).padStart(2, '0')}`);
const idxCache = new WeakMap();
function idxOf(rows, k) {
  let m = idxCache.get(rows);
  if (!m) { m = new Map(rows.map((r, i) => [r[0], i])); idxCache.set(rows, m); }
  return m.has(k) ? m.get(k) : -1;
}
function hoverLegend(charts, box, getRows, render) {
  const el = document.createElement('div'); el.className = 'hov';
  box.style.position = 'relative'; box.appendChild(el);
  const show = (i) => { const rows = getRows(); if (!rows?.length) { el.innerHTML = ''; return; } if (i == null || i < 0) i = rows.length - 1; el.innerHTML = render(rows, i); };
  (Array.isArray(charts) ? charts : [charts]).forEach((c) => c.subscribeCrosshairMove((p) => {
    if (!p || p.time === undefined) return show(null);
    show(idxOf(getRows(), tkey(p.time)));
  }));
  show(null);
  return show;
}
const nf = (v, d) => (v == null ? '–' : v.toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d }));
const autoDec = (v) => (Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 2 : Math.abs(v) >= 1 ? 2 : 4);
function ohlcText(rows, i, { dec, unit = '', extra = '', bp = false } = {}) {
  const b = rows[i], p = rows[i - 1]; const d = dec ?? autoDec(b[4]);
  const chg = p ? (b[4] / p[4] - 1) * 100 : null;
  const u = unit ? `<span class="muted">${unit}</span>` : '';
  return `<b>${fmtT(b[0])}</b> 시 ${nf(b[1], d)} · 고 ${nf(b[2], d)} · 저 ${nf(b[3], d)} · 종 <b>${nf(b[4], d)}</b>${u}`
    + (chg != null ? (bp ? ` <span class="${cls(chg)}">${b[4] - p[4] > 0 ? '+' : ''}${((b[4] - p[4]) * 100).toFixed(0)}bp</span>` : ` <span class="${cls(chg)}">${chg > 0 ? '+' : ''}${chg.toFixed(2)}%</span>`) : '') + extra;
}
function lineText(rows, i, { dec = 2, unit = '', bp = false } = {}) {
  const v = rows[i][1], p = rows[i - 1]?.[1];
  let chg = '';
  if (p != null) { const df = v - p; chg = bp ? `${df > 0 ? '+' : ''}${(df * 100).toFixed(0)}bp` : `${df > 0 ? '+' : ''}${nf(df, dec)}`; chg = ` <span class="${cls(df)}">(${chg})</span>`; }
  return `<b>${fmtT(rows[i][0])}</b> <b>${nf(v, dec)}</b>${unit ? `<span class="muted">${unit}</span>` : ''}${chg}`;
}

// ------------------------------------------------------------ 지표 카드
const cardHTML = (id, title, wide = false, extra = '') => `<div class="card ${wide ? 'wide' : ''}" id="${id}">
  <div class="chead"><div><div class="ctitle">${title}</div><div class="cval"></div><div class="cchg"></div></div><div class="ranges"></div></div>
  <div class="cbox"></div>${extra}</div>`;

function cardHeader(card, data, { dec = 2, unit = '', bp = false, badge = '' } = {}) {
  if (!data?.length) { $('.cval', card).textContent = '–'; $('.cchg', card).innerHTML = '<span class="muted">데이터 없음</span>'; return; }
  const last = data.at(-1), prev = data.at(-2);
  const v = last[last.length === 2 ? 1 : 4], p = prev ? prev[prev.length === 2 ? 1 : 4] : null;
  $('.cval', card).innerHTML = `${fnum(v, dec)}${unit ? `<span class="small muted"> ${unit}</span>` : ''}${badge}`;
  if (p == null) return;
  const diff = v - p;
  const chg = bp ? `${diff > 0 ? '+' : ''}${(diff * 100).toFixed(0)}bp` : `${diff > 0 ? '+' : ''}${fnum(diff, dec)} (${fp((v / p - 1) * 100)})`;
  $('.cchg', card).innerHTML = `<span class="${cls(diff)}">${chg}</span> <span class="cdate">${fmtDate(last[0])}</span>`;
}

function ohlcCard(id, s, { def = '1Y', ranges = ['3M', '6M', '1Y', '3Y'], dec = 2, unit = '', bp = false, bands = [] } = {}) {
  const card = document.getElementById(id); if (!card || !s) return;
  cardHeader(card, s.data, { dec, unit, bp });
  const th = theme();
  const ch = makeChart($('.cbox', card));
  const cs = ch.addCandlestickSeries({ upColor: th.up, downColor: th.down, wickUpColor: th.up, wickDownColor: th.down, borderVisible: false, priceLineVisible: false });
  cs.setData(s.data.map((b) => ({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] })));
  bands.forEach((b) => cs.createPriceLine({ price: b, color: th.muted, lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
  bindRanges($('.ranges', card), ch, s.data, ranges, def);
  hoverLegend(ch, $('.cbox', card), () => s.data, (r, i) => ohlcText(r, i, { dec, unit, bp }));
}
const ALL_R = ['3M', '6M', '1Y', '3Y', '5Y', '10Y'];
function anyCard(id, s, o) { if (s?.type === 'ohlc') ohlcCard(id, s, { ranges: ALL_R, ...o }); else lineCard(id, s, o); }

function lineCard(id, s, { color, dec = 2, unit = '', bp = false, def = '3Y', ranges = ['3M', '6M', '1Y', '3Y', '5Y', '10Y'], bands = [], badge = '' } = {}) {
  const card = document.getElementById(id); if (!card || !s) return;
  cardHeader(card, s.data, { dec, unit, bp, badge });
  const ch = makeChart($('.cbox', card));
  const ser = ch.addAreaSeries({ lineColor: color, topColor: rgba(color, 0.22), bottomColor: rgba(color, 0.02), lineWidth: 2, priceLineVisible: false, priceFormat: { type: 'price', precision: dec, minMove: 1 / 10 ** dec } });
  ser.setData(s.data.map((p) => ({ time: p[0], value: p[1] })));
  const th = theme();
  bands.forEach((b) => ser.createPriceLine({ price: b, color: th.muted, lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
  bindRanges($('.ranges', card), ch, s.data, ranges, def);
  hoverLegend(ch, $('.cbox', card), () => s.data, (r, i) => lineText(r, i, { dec, unit, bp }));
}

function sma(v, n) { const out = []; let s = 0; for (let i = 0; i < v.length; i++) { s += v[i]; if (i >= n) s -= v[i - n]; out.push(i >= n - 1 ? s / n : null); } return out; }
function rsi(v, n = 14) {
  const out = Array(v.length).fill(null); let g = 0, l = 0;
  for (let i = 1; i < v.length; i++) {
    const d = v[i] - v[i - 1], up = Math.max(d, 0), dn = Math.max(-d, 0);
    if (i <= n) { g += up; l += dn; if (i === n) { g /= n; l /= n; out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); } }
    else { g = (g * (n - 1) + up) / n; l = (l * (n - 1) + dn) / n; out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); }
  }
  return out;
}

function maRsiCard(id, s, MA = [[5, '#e5489b'], [20, '#f0a020'], [60, '#2fa84f'], [120, '#8a8a95']], ranges = ['3M', '6M', '1Y', '3Y'], def = '1Y') {
  const card = document.getElementById(id); if (!card || !s) return;
  cardHeader(card, s.data);
  const th = theme();
  const main = makeChart($('.cbox', card));
  const cs = main.addCandlestickSeries({ upColor: th.up, downColor: th.down, wickUpColor: th.up, wickDownColor: th.down, borderVisible: false, priceLineVisible: false });
  const d = s.data, closes = d.map((b) => b[4]);
  cs.setData(d.map((b) => ({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] })));
  MA.forEach(([n, color]) => {
    const m = sma(closes, n);
    main.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
      .setData(d.map((b, i) => (m[i] == null ? { time: b[0] } : { time: b[0], value: m[i] })));
  });
  const vs = main.addHistogramSeries({ priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false });
  main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  vs.setData(d.map((b) => ({ time: b[0], value: b[5], color: rgba(b[4] >= b[1] ? th.up : th.down, 0.35) })));

  const rbox = $('.rsibox', card);
  const rc = makeChart(rbox, { rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.1, bottom: 0.1 } } });
  const r = rsi(closes, 14);
  const rs = rc.addLineSeries({ color: '#f07f20', lineWidth: 1.5, priceLineVisible: false, priceFormat: { type: 'price', precision: 1, minMove: 0.1 } });
  rs.setData(d.map((b, i) => (r[i] == null ? { time: b[0] } : { time: b[0], value: r[i] })));
  [70, 30].forEach((p) => rs.createPriceLine({ price: p, color: th.muted, lineWidth: 1, lineStyle: 2, axisLabelVisible: true }));
  // 두 차트 시간축 동기화
  let busy = false;
  const link = (a, b) => a.timeScale().subscribeVisibleLogicalRangeChange((lr) => { if (busy || !lr) return; busy = true; b.timeScale().setVisibleLogicalRange(lr); busy = false; });
  link(main, rc); link(rc, main);
  bindRanges($('.ranges', card), main, d, ranges, def);
  const mas = MA.map(([n]) => [n, sma(closes, n)]);
  hoverLegend([main, rc], $('.cbox', card), () => d, (rows, i) => ohlcText(rows, i, {
    extra: `<br>${mas.map(([n, m]) => `${n}일 ${m[i] == null ? '–' : nf(m[i], autoDec(m[i]))}`).join(' · ')} · <b>RSI ${r[i] == null ? '–' : r[i].toFixed(1)}</b>` }));
  const lastR = r.at(-1);
  $('.legend', card).innerHTML = MA.map(([n, c]) => `<span><i style="background:${c}"></i>${n}일선</span>`).join('') +
    `<span><i style="background:#f07f20"></i>RSI(14) ${lastR != null ? lastR.toFixed(1) : '–'}</span>`;
}

function fundsCard(id, dep, cre) {
  const card = document.getElementById(id); if (!card) return;
  const th = theme();
  const ch = makeChart($('.cbox', card), { leftPriceScale: { visible: true, borderVisible: false } });
  const series = [[dep, th.accent, 'right'], [cre, '#f07f20', 'left']];
  series.forEach(([s, color, side]) => {
    if (!s?.data?.length) return;
    ch.addLineSeries({ color, lineWidth: 2, priceScaleId: side, priceLineVisible: false, priceFormat: { type: 'price', precision: 1, minMove: 0.1 } })
      .setData(s.data.map((p) => ({ time: p[0], value: p[1] })));
  });
  const ref = dep?.data?.length ? dep.data : cre?.data || [];
  bindRanges($('.ranges', card), ch, ref, ['3M', '6M', '1Y', '3Y'], '3Y');
  const cmap = new Map((cre?.data || []).map((p) => [p[0], p[1]]));
  hoverLegend(ch, $('.cbox', card), () => ref, (rows, i) => {
    const day = rows[i][0], dv = dep?.data?.length ? rows[i][1] : null, cv = cmap.get(day);
    return `<b>${fmtT(day)}</b> 예탁금 <b>${nf(dv, 1)}조</b> · 신용잔고 <b>${nf(cv, 2)}조</b>`;
  });
  const tail = (s) => { if (!s?.data?.length) return '–'; const a = s.data.at(-1), b = s.data.at(-2); const df = b ? a[1] - b[1] : null; return `<b>${fnum(a[1], 1)}조</b> <span class="${cls(df)} small">${df == null ? '' : (df > 0 ? '+' : '') + fnum(df, 2)}</span>`; };
  $('.cval', card).innerHTML = `<span style="font-size:15px">예탁금 ${tail(dep)} · 신용 ${tail(cre)}</span>`;
  const ld = (dep?.data || cre?.data || []).at(-1);
  $('.cchg', card).innerHTML = ld ? `<span class="cdate">${fmtDate(ld[0])} 기준 · 금융투자협회</span>` : '';
  $('.legend', card).innerHTML = `<span><i style="background:${th.accent}"></i>투자자 예탁금 (오른쪽 축, 조원)</span><span><i style="background:#f07f20"></i>신용잔고 (왼쪽 축, 조원)</span>`;
}

// ------------------------------------------------------------ 리스트 + 차트 패널
function rowHTML(it, i, metric, extra = '') {
  const ind = it.industry ? `<span class="ind">(${esc(it.industry)})</span>` : '';
  const tags = (it.ath ? '<span class="tag ath">역대</span>' : '') + (it.small && !it.cap ? '<span class="tag">소형</span>' : '');
  const hold = it.holdings !== undefined;
  return `<button class="lrow" data-i="${i}" title="${esc(it.name)} ${esc(it.industry || '')}">
    <span class="rk">${hold ? '<span class="caret" title="구성종목 보기">▶</span>' : ''}${extra || `${i + 1}위`}</span>
    <span class="nm"><b>${esc(it.name)}</b>${hold ? `<span class="ind">${esc(it.ticker)}</span>` : ''}${tags}${ind}</span>
    <span class="pc ${cls(it[metric])}">${fmetric(it, metric)}</span></button>${hold ? `<div class="hwrap" data-h="${i}" hidden>${holdsHTML(it)}</div>` : ''}`;
}
const detailHTML = () => `<div class="detail"><div class="dhead"><div><div class="dname"></div><div class="dsub"></div></div><div class="dprice"><div class="v"></div><div class="c"></div></div></div>
  <div class="ranges" style="justify-content:flex-start;margin-top:8px"></div><div class="dbox"></div><div class="dextra"></div><div class="dlinks"></div></div>`;

const CAPS = [['L', '대형 · $10B 이상'], ['M', '중형 · $1B~10B'], ['S', '소형 · $0.1B~1B'], ['U', '시총 미확인']];
const hasCaps = (items) => items.some((x) => x.cap);
const defCap = (items) => (CAPS.find(([k]) => items.some((x) => (x.cap || 'U') === k)) || ['L'])[0];
function capbarHTML(id, items, cur) {
  return `<div class="capbar" data-p="${id}">${CAPS.map(([k, label]) => { const n = items.filter((x) => (x.cap || 'U') === k).length;
    return k === 'U' && !n ? '' : `<button data-c="${k}" class="${k === cur ? 'on' : ''}">${label} <span class="n">${n}</span></button>`; }).join('')}</div>`;
}
function panelHTML(id, title, items, opts) {
  const caps = hasCaps(items);
  const cur = caps ? defCap(items) : null;
  const shown = caps ? items.filter((x) => (x.cap || 'U') === cur) : items;
  const note = caps && opts.fx ? '<span class="small muted" style="font-weight:400">(시총은 달러 환산)</span>' : '';
  const head = `<h2 class="sec">${title} <span class="n">${items.length}</span>${note}${opts.copy ? '<button class="copy" data-copy="' + id + '">텍스트 복사</button>' : ''}</h2>${opts.tools || ''}${caps ? capbarHTML(id, items, cur) : ''}`;
  if (!items.length) return head + '<div class="empty">해당 종목 없음</div>';
  const rows = shown.map((it, i) => rowHTML(it, i, opts.metric)).join('');
  return `${head}<div class="panel" id="${id}"><div class="list">${rows}</div>${detailHTML()}</div>`;
}

function toggleHold(el, r, i) {
  const h = el.querySelector(`[data-h="${i}"]`); if (!h) return;
  h.hidden = !h.hidden; const c = $('.caret', r); if (c) c.textContent = h.hidden ? '▶' : '▼';
}
function bindPanel(id, all, opts) {
  const el = document.getElementById(id); if (!el) return;
  const caps = hasCaps(all);
  const items = caps ? all.filter((x) => (x.cap || 'U') === defCap(all)) : all;
  const p = { items, opts, chart: null, seq: 0 };
  panels.set(id, p);
  const bar = document.querySelector(`.capbar[data-p="${id}"]`);
  if (bar) bar.onclick = (e) => {
    const b = e.target.closest('button'); if (!b) return;
    bar.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
    p.items = all.filter((x) => (x.cap || 'U') === b.dataset.c);
    $('.list', el).innerHTML = p.items.map((it, i) => rowHTML(it, i, opts.metric)).join('') || '<p class="muted small" style="padding:10px 14px">해당 종목 없음</p>';
    $('.list', el).scrollTop = 0;
    if (p.items.length) selectItem(id, 0);
  };
  $('.list', el).onclick = (e) => {
    const r = e.target.closest('.lrow'); if (!r) return;
    const i = Number(r.dataset.i);
    if (e.target.closest('.caret')) { toggleHold(el, r, i); return; }  // 화살표: 구성종목만 펼침/접기
    selectItem(id, i);  // 이름: 차트만
  };
  if (items.length) selectItem(id, 0);
}

async function selectItem(id, i) {
  const p = panels.get(id); const el = document.getElementById(id); if (!p || !el) return;
  const it = p.items[i]; const seq = ++p.seq;
  el.querySelectorAll('.lrow').forEach((r) => r.classList.toggle('on', Number(r.dataset.i) === i));
  const det = $('.detail', el), box = $('.dbox', det);
  const mk = p.opts.chartMarket;
  const meta = p.opts.showMeta ? [it.rs != null ? `RS ${it.rs}` : '', it.mcap ? `시총 ${fcap(it.mcap, mk)}` : '', it.per != null ? `PER ${it.per}` : '', it.psr != null ? `PSR ${it.psr}` : ''].filter(Boolean).join(' · ') : '';
  $('.dname', det).innerHTML = `${esc(it.name)}${meta ? ` <span class="dmeta">(${meta})</span>` : ''}`;
  const sub = [mk === 'etf' ? it.ticker : (mk === 'us' ? it.ticker : code(it.ticker)), it.name_local, it.industry].filter(Boolean).join(' · ');
  const ma = [it.above50 === false ? '50일선 아래' : '', it.above200 === false ? '200일선 아래' : ''].filter(Boolean).join(' · ');
  const mom = it.rel1w != null ? `시장 대비 1주 ${fpp(it.rel1w)} · 1달 ${fpp(it.rel1m)}` : '';
  $('.dsub', det).innerHTML = [esc(sub), mom, ma ? `<span class="matag">${ma}</span>` : ''].filter(Boolean).join(' · ');
  const m = p.opts.metric;
  $('.v', det).textContent = fnum(it.close);
  $('.c', det).innerHTML = m === 'score' ? `<span class="${cls(it.d1)}">일간 ${fp(it.d1)}</span>` : `<span class="${cls(it[m])}">${m === 'w1' ? '주간 ' : '일간 '}${fp(it[m])}</span>`;
  $('.dlinks', det).innerHTML = links(it.ticker, mk);
  $('.dextra', det).innerHTML = p.opts.extra ? p.opts.extra(it) : '';
  dropChart(p.chart); p.chart = null;
  box.innerHTML = '<p class="muted small">차트 불러오는 중…</p>';
  let data;
  try { data = await getJSON(`data/charts/${mk}/${safe(it.ticker)}.json`); }
  catch { if (seq === p.seq) box.innerHTML = '<p class="muted small">차트 데이터가 없습니다.</p>'; return; }
  if (seq !== p.seq) return;
  if (!(await loadLWC())) { box.innerHTML = '<p class="muted small">차트 라이브러리를 불러오지 못했습니다.</p>'; return; }
  box.innerHTML = '';
  try {
    const th = theme();
    const ch = makeChart(box); p.chart = ch;
    const cs = ch.addCandlestickSeries({ upColor: th.up, downColor: th.down, wickUpColor: th.up, wickDownColor: th.down, borderVisible: false });
    cs.setData(data.bars.map((b) => ({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] })));
    const vs = ch.addHistogramSeries({ priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false });
    ch.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vs.setData(data.bars.map((b) => ({ time: b[0], value: b[5], color: rgba(b[4] >= b[1] ? th.up : th.down, 0.35) })));
    if (it.ref != null) cs.createPriceLine({ price: it.ref, color: th.muted, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '직전 52주 고가' });
    const wk = data.weekly || [];
    const keys = ['1M', '3M', '6M', '1Y', ...(wk.length > 60 ? ['3Y'] : []), ...(wk.length > 160 ? ['5Y'] : [])];
    let mode = 'd';
    hoverLegend(ch, box, () => (mode === 'w' ? wk : data.bars), (r, i) => ohlcText(r, i, { extra: mode === 'w' ? ' <span class="muted">(주봉)</span>' : '' }));
    const toC = (b) => ({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] });
    const toV = (b) => ({ time: b[0], value: b[5], color: rgba(b[4] >= b[1] ? th.up : th.down, 0.35) });
    const apply = (k) => {
      const w = k === '3Y' || k === '5Y';
      if (w && mode !== 'w') { cs.setData(wk.map(toC)); vs.setData(wk.map(toV)); mode = 'w'; }
      if (!w && mode !== 'd') { cs.setData(data.bars.map(toC)); vs.setData(data.bars.map(toV)); mode = 'd'; }
      setRange(ch, (w ? wk : data.bars).map((b) => [b[0]]), RANGES[k]);
    };
    const rb = $('.ranges', det); const def = p.opts.defRange || '6M';
    rb.innerHTML = keys.map((k) => `<button data-k="${k}" class="${k === def ? 'on' : ''}">${k}${k === '3Y' || k === '5Y' ? '<span class="small"> 주봉</span>' : ''}</button>`).join('');
    rb.onclick = (e) => { const b = e.target.closest('button'); if (!b) return; rb.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b)); apply(b.dataset.k); };
    apply(def);
  } catch (e) { console.error(e); box.innerHTML = `<p class="muted small">차트 오류: ${esc(e.message || e)}</p>`; }
}
RANGES['1M'] = 1;

function links(t, mk) {
  const y = `<a href="https://finance.yahoo.com/quote/${encodeURIComponent(t)}" target="_blank" rel="noopener">Yahoo Finance ↗</a>`;
  if (mk === 'jp') return y + `<a href="https://kabutan.jp/stock/?code=${encodeURIComponent(code(t))}" target="_blank" rel="noopener">株探 ↗</a>`;
  if (mk === 'tw') return y + `<a href="https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID=${encodeURIComponent(code(t))}" target="_blank" rel="noopener">Goodinfo ↗</a>`;
  if (mk === 'kr') return `<a href="https://finance.naver.com/item/main.naver?code=${encodeURIComponent(code(t))}" target="_blank" rel="noopener">네이버 금융 ↗</a>` + y;
  if (mk === 'etf') return y + `<a href="https://stockanalysis.com/etf/${encodeURIComponent(t.toLowerCase())}/holdings/" target="_blank" rel="noopener">전체 구성종목 ↗</a>`;
  return y + `<a href="https://finviz.com/quote.ashx?t=${encodeURIComponent(t)}" target="_blank" rel="noopener">Finviz ↗</a>`;
}

function highsText(day) {
  const t = TABS[day.market];
  const m = new Map();
  day.newhigh.forEach((i) => { const k = i.industry || '기타'; if (!m.has(k)) m.set(k, []); m.get(k).push(i); });
  const L = [`${t.flag} ${t.name} 신고가 · ${fmtDate(day.date)}`, day.criteria, ''];
  [...m.entries()].sort((a, b) => (b[1][0].d1 ?? 0) - (a[1][0].d1 ?? 0)).forEach(([k, arr]) => L.push(`(${k}) ` + arr.map((i) => `${i.name}${i.ath ? ' 🏆' : ''} ${fp(i.d1, 1)}`).join(', ')));
  L.push('', `🔗 ${location.href}`);
  return L.join('\n');
}

// ------------------------------------------------------------ 페이지
function stockSections(day, mk) {
  if (!day) return '<div class="empty">아직 종목 데이터가 없습니다.</div>';
  return `<p class="muted small" style="margin:18px 0 -14px">${fmtDate(day.date)} 기준 · 집계 ${day.priced?.toLocaleString()}종목 · 신고가: ${esc(day.criteria)} · 오른쪽 차트는 왼쪽에서 종목을 누르면 바뀝니다</p>`
    + panelHTML(`${mk}-high`, '신고가', day.newhigh, { metric: 'd1', copy: true, fx: mk !== 'us' })
    + (day.rising ? panelHTML(`${mk}-rise`, `최근 시장 대비 강세 <span class="small muted">(1주·1달 모두 ${BENCH[mk] || '지수'}보다 강한 종목 · 숫자는 1주+1달 초과수익 합계)</span>`, day.rising, { metric: 'score', fx: mk !== 'us' }) : '')
    + panelHTML(`${mk}-d1`, '일간 상승률 상위', day.top_d1, { metric: 'd1', fx: mk !== 'us' })
    + panelHTML(`${mk}-w1`, wkTitle(day), day.top_w1, { metric: 'w1', fx: mk !== 'us' });
}
function bindStocks(day, mk) {
  if (!day) return;
  const showMeta = mk !== 'kr';
  bindPanel(`${mk}-high`, day.newhigh, { metric: 'd1', chartMarket: mk, defRange: '1Y', showMeta });
  if (day.rising) bindPanel(`${mk}-rise`, day.rising, { metric: 'score', chartMarket: mk, defRange: '6M', showMeta });
  bindPanel(`${mk}-d1`, day.top_d1, { metric: 'd1', chartMarket: mk, defRange: '6M', showMeta });
  bindPanel(`${mk}-w1`, day.top_w1, { metric: 'w1', chartMarket: mk, defRange: '6M', showMeta });
  const btn = document.querySelector(`[data-copy="${mk}-high"]`);
  if (btn) btn.onclick = async () => { try { await navigator.clipboard.writeText(highsText(day)); btn.textContent = '복사됨 ✓'; } catch { btn.textContent = '복사 실패'; } setTimeout(() => (btn.textContent = '텍스트 복사'), 1500); };
}

const BENCH = { us: 'S&P500', jp: '니케이225', tw: '가권지수' };
function wkTitle(day) {
  const w = day?.w1_week; if (!w) return '주간 상승률 상위';
  const [a, b] = w.split('~'); const f = (x) => x.slice(5).replace('-', '/');
  return `주간 상승률 상위 <span class="small muted">(${f(a)}~${f(b.slice(0, 10))} 한 주 · 매주 금요일 장 마감 후 갱신)</span>`;
}
async function pageUS(day) {
  const mac = await getJSON('data/macro/us.json').catch(() => null);
  const S = mac?.series || {};
  const fgNow = S.fg?.now ? `<span class="badge">${esc(FG_KO[S.fg.now.rating] || S.fg.now.rating)}</span>` : '';
  const RSI_BOX = '<div class="rsibox"></div><div class="legend"></div>';
  let html = `<h2 class="sec">지수</h2><div class="grid">${cardHTML('c-dji', '다우존스 (일봉 · 이동평균 · RSI)', true, RSI_BOX)}${cardHTML('c-ixic', '나스닥 종합 (일봉 · 이동평균 · RSI)', true, RSI_BOX)}${cardHTML('c-spx', 'S&P 500 (일봉 · 이동평균 · RSI)', true, RSI_BOX)}</div>
    <h2 class="sec">변동성 · 심리</h2><div class="grid">${cardHTML('c-vix', 'VIX (변동성지수) · 일봉', true)}</div>
    <div class="grid two" style="margin-top:12px">${cardHTML('c-fg', '공포탐욕지수 <span class="small muted">CNN</span>')}${cardHTML('c-pc', 'Put/Call 비율 <span class="small muted">5일 평균</span>')}</div>
    <h2 class="sec">미국 국채 금리</h2><div class="grid">${cardHTML('c-u2', '2년물 <span class="small muted">(일봉 자료 없음 · 재무부 종가)</span>', true)}${cardHTML('c-u10', '10년물 · 일봉', true)}${cardHTML('c-u30', '30년물 · 일봉', true)}</div>`;
  html += stockSections(day, 'us');
  $('#main').innerHTML = html;
  const th = theme();
  const IMA = [[5, '#e5489b'], [20, '#f0a020'], [50, '#2fa84f'], [120, '#8a5cf6'], [200, '#8a8a95']];
  const IR = ['3M', '6M', '1Y', '3Y', '5Y'];
  maRsiCard('c-dji', S.dji, IMA, IR, '1Y'); maRsiCard('c-ixic', S.ixic, IMA, IR, '1Y'); maRsiCard('c-spx', S.spx, IMA, IR, '1Y');
  anyCard('c-vix', S.vix, { color: th.up, def: '1Y', bands: [20, 30] });
  lineCard('c-fg', S.fg, { color: th.accent, dec: 1, def: '1Y', bands: [25, 50, 75], badge: fgNow });
  lineCard('c-pc', S.pc, { color: '#8a5cf6', dec: 3, def: '1Y', bands: [1] });
  [['c-u2', 'ust2'], ['c-u10', 'ust10'], ['c-u30', 'ust30']].forEach(([id, k]) => anyCard(id, S[k], { color: '#2fa84f', unit: '%', bp: true, def: '1Y', dec: 3 }));
  bindStocks(day, 'us');
}

async function pageKR(day) {
  const mac = await getJSON('data/macro/kr.json').catch(() => null);
  const S = mac?.series || {};
  const RB = '<div class="rsibox"></div><div class="legend"></div>';
  let html = `<h2 class="sec">지수</h2><div class="grid">${cardHTML('c-kospi', '코스피 (일봉 · 이동평균 · RSI)', true, RB)}${cardHTML('c-kosdaq', '코스닥 (일봉 · 이동평균 · RSI)', true, RB)}${cardHTML('c-vkospi', 'VKOSPI · 코스피200 변동성지수 <span class="small muted">(일봉 · 한국거래소, 하루 늦게 반영)</span>', true)}</div>
    <h2 class="sec">증시 자금</h2><div class="grid">${cardHTML('c-funds', '투자자 예탁금 · 신용잔고', true, '<div class="legend"></div>')}</div>`;
  html += stockSections(day, 'kr');
  $('#main').innerHTML = html;
  maRsiCard('c-kospi', S.kospi, undefined, ['3M', '6M', '1Y', '3Y'], '1Y');
  maRsiCard('c-kosdaq', S.kosdaq, undefined, ['3M', '6M', '1Y', '3Y'], '1Y');
  if (S.vkospi) ohlcCard('c-vkospi', S.vkospi, { ranges: ['3M', '6M', '1Y', '3Y'], def: '1Y', bands: [20, 30] });
  else $('#c-vkospi .cbox').innerHTML = '<p class="muted small">데이터 준비 중입니다.</p>';
  fundsCard('c-funds', S.deposit, S.credit);
  bindStocks(day, 'kr');
}

async function pageIdx(day, mk, title) {
  const mac = await getJSON(`data/macro/${mk}.json`).catch(() => null);
  $('#main').innerHTML = `<h2 class="sec">지수</h2><div class="grid">${cardHTML(`c-${mk}idx`, `${title} (일봉 · 이동평균 · RSI)`, true, '<div class="rsibox"></div><div class="legend"></div>')}</div>` + stockSections(day, mk);
  if (mac?.series?.index) maRsiCard(`c-${mk}idx`, mac.series.index, undefined, ['3M', '6M', '1Y', '3Y'], '1Y');
  else $(`#c-${mk}idx .cbox`).innerHTML = '<p class="muted small">지수 데이터가 아직 없습니다.</p>';
  bindStocks(day, mk);
}
const pageTW = (day) => pageIdx(day, 'tw', '대만 가권지수');
const pageJP = (day) => pageIdx(day, 'jp', '니케이 225');

function etfExtra(it) {
  const hs = it.shares || [];
  if (!hs.length) return '<div class="shares"><h4>좌수 변동</h4><p class="muted small">아직 기록이 없습니다. 매일 쌓입니다.</p></div>';
  const rows = hs.slice().reverse().slice(0, 10).map((r, i, a) => {
    const prev = a[i + 1]?.[1]; const df = prev != null ? r[1] - prev : null;
    return `<tr><td>${r[0]}</td><td>${r[1].toLocaleString()}</td><td class="${cls(df)}">${df == null ? '–' : (df > 0 ? '+' : '') + df.toLocaleString()}</td></tr>`;
  }).join('');
  return `<div class="shares"><h4>좌수 변동 <span class="small muted">(추정: 순자산÷NAV, 매일 기록)</span></h4><table><tr><th>날짜</th><th>좌수</th><th>전일 대비</th></tr>${rows}</table></div>`;
}
function holdsHTML(it) {
  if (!it.holdings?.length) return '<div class="holds muted">구성종목 정보 없음</div>';
  return `<div class="holds"><table>${it.holdings.map((h) => `<tr><td class="sym">${esc(h.symbol)}</td><td>${esc(h.name)}</td><td>${h.pct.toFixed(2)}%</td></tr>`).join('')}</table></div>`;
}

async function pageETF(day) {
  if (!day) { $('#main').innerHTML = '<div class="empty">아직 ETF 데이터가 없습니다.</div>'; return; }
  const sk = day.skipped || {};
  const tool = `<p class="muted small" style="margin:-4px 0 8px">미국 상장 ETF 중 순자산 1조원(${day.min_aum_usd ? '$' + (day.min_aum_usd / 1e8).toFixed(1) + '억' : '환산'}) 이상 · 상장 6개월 이상 · 구성종목 10개 이상 · 레버리지·인버스 제외 ${day.priced?.toLocaleString()}개 기준 · ${fmtDate(day.date)} · ▶ 누르면 상위 구성종목 10개</p>`;
  const tops = (v) => (Array.isArray(v) ? v : v?.unlev || []).map((x) => ({ ...x, holdings: x.holdings || [] }));
  const d1 = tops(day.top_d1), w1 = tops(day.top_w1);
  const REG = { us: '🇺🇸 미국', jp: '🇯🇵 일본' };
  const watch = ['us', 'jp'].flatMap((rg) => day.groups.filter((g) => (g.region || (g.name.includes('일본') ? 'jp' : 'us')) === rg)
    .flatMap((g) => g.items.map((it) => ({ ...it, group: g.name, region: rg }))));
  let rows = '';
  watch.forEach((it, i) => {
    if (it.region !== watch[i - 1]?.region) rows += `<div class="lregion">${REG[it.region]}</div>`;
    if (it.group !== watch[i - 1]?.group) rows += `<div class="lgroup">${esc(it.group)}</div>`;
    rows += `<button class="lrow" data-i="${i}"><span class="rk"><span class="caret" title="구성종목 보기">▶</span></span><span class="nm"><b>${esc(it.label)}</b><span class="ind">${esc(it.ticker)}</span></span><span class="pc ${cls(it.d1)}">${fp(it.d1)}</span></button><div class="hwrap" data-h="${i}" hidden>${holdsHTML(it)}</div>`;
  });
  const st = day.strength || [];
  const pick = (k) => st.filter((x) => x.trend === k);
  const line = (k, label, c) => { const a = pick(k); return `<div class="srow"><span class="slab ${c}">${label}</span><span>${a.length ? a.map((x) => `<span class="si" title="${esc(x.ticker)} · 1주 ${fpp(x.rel1w)} · 1달 ${fpp(x.rel1m)} · RS ${x.rs ?? '–'}"><b>${esc(x.label)}</b><span class="muted">${fpp(x.rel1w)}/${fpp(x.rel1m)}${x.rs != null ? ' · RS ' + x.rs : ''}${x.above50 === false ? ' · <span class="matag">50일선↓</span>' : ''}</span></span>`).join('') : '<span class="muted">없음</span>'}</span></div>`; };
  const strengthBox = st.length ? `<div class="strength"><div class="shead">미국 섹터·테마 흐름 <span class="muted small">· 숫자: S&P500 대비 1주/1달 초과수익(%p) · RS · ${fmtDate(day.date)}</span></div>
    ${line('강세', '강한 섹터', 'up')}${line('횡보', '횡보 섹터', '')}${line('약세', '하락 섹터', 'down')}</div>` : '';
  $('#main').innerHTML = panelHTML('etf-d1', '일간 상승률 상위', d1, { metric: 'd1', tools: tool })
    + panelHTML('etf-w1', wkTitle(day), w1, { metric: 'w1' })
    + `<h2 class="sec">관심 ETF <span class="n">${watch.length}</span></h2><p class="muted small" style="margin:-4px 0 8px">이름을 누르면 오른쪽에 차트와 좌수 변동이, ▶ 화살표를 누르면 상위 구성종목 10개가 나옵니다.</p>
       <div class="panel" id="etf-watch"><div class="lcol"><div class="list">${rows}</div>${strengthBox}</div>${detailHTML()}</div>`;
  bindPanel('etf-d1', d1, { metric: 'd1', chartMarket: 'etf', defRange: '6M' });
  bindPanel('etf-w1', w1, { metric: 'w1', chartMarket: 'etf', defRange: '6M' });
  // 관심 ETF: 이름 클릭 → 구성종목 펼침/접기 + 차트
  const el = document.getElementById('etf-watch');
  panels.set('etf-watch', { items: watch, opts: { metric: 'd1', chartMarket: 'etf', defRange: '1Y', extra: etfExtra }, chart: null, seq: 0 });
  $('.list', el).onclick = (e) => {
    const r = e.target.closest('.lrow'); if (!r) return;
    const i = Number(r.dataset.i);
    if (e.target.closest('.caret')) { toggleHold(el, r, i); return; }
    selectItem('etf-watch', i);
  };
  selectItem('etf-watch', 0);
}

// ------------------------------------------------------------ 라우팅
function parseHash() {
  const [t, d] = location.hash.replace(/^#/, '').split('/');
  if (TABS[t]) state.tab = t;
  state.date = /^\d{4}-\d{2}-\d{2}$/.test(d || '') ? d : null;
}
const go = (p) => { location.hash = `${p.tab ?? state.tab}/${p.date ?? state.date ?? ''}`; };

async function render() {
  const seq = ++renderSeq;
  parseHash();
  destroyAll();
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.t === state.tab));
  const dates = INDEX?.[state.tab] || [];
  const date = dates.includes(state.date) ? state.date : dates[0];
  const sel = $('#date');
  sel.innerHTML = dates.map((d) => `<option value="${d}" ${d === date ? 'selected' : ''}>${fmtDate(d)}</option>`).join('') || '<option>데이터 없음</option>';
  const i = dates.indexOf(date);
  $('#prev').disabled = !date || i >= dates.length - 1;
  $('#next').disabled = !date || i <= 0;
  $('#main').innerHTML = '<p class="muted">불러오는 중…</p>';
  const okLib = await loadLWC();
  let day = null;
  if (date) day = await getJSON(`data/${state.tab}/${date}.json`).catch(() => null);
  if (seq !== renderSeq) return;
  if (!okLib) { $('#main').innerHTML = '<div class="empty">차트 라이브러리를 불러오지 못했습니다. 새로고침해 주세요.</div>'; return; }
  try {
    await ({ us: pageUS, kr: pageKR, jp: pageJP, tw: pageTW, etf: pageETF }[state.tab])(day);
  } catch (e) { console.error(e); $('#main').innerHTML = `<div class="empty">화면을 그리다 오류가 났습니다: ${esc(e.message || e)}</div>`; }
}

async function init() {
  $('#tabs').onclick = (e) => { const t = e.target.closest('button')?.dataset.t; if (t) go({ tab: t, date: '' }); };
  $('#date').onchange = (e) => go({ date: e.target.value });
  const step = (k) => { const ds = INDEX?.[state.tab] || []; const i = ds.indexOf($('#date').value); const d = ds[i + k]; if (d) go({ date: d }); };
  $('#prev').onclick = () => step(1);
  $('#next').onclick = () => step(-1);
  window.addEventListener('hashchange', render);
  try { INDEX = await (await fetch(`data/index.json?t=${Date.now()}`, { cache: 'no-cache' })).json(); } catch { INDEX = {}; }
  render();
}
init();
