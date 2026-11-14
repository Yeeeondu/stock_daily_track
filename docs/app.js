// 신고가·신저가 보드 — 정적 사이트 (GitHub Pages)
// 주소 형식: #<market>/<view>/<date>   예) #jp/newhigh/2026-11-12
const MARKETS = { jp: { flag: '🇯🇵', name: '일본' }, us: { flag: '🇺🇸', name: '미국' } };
const VIEWS = { newhigh: '신고가', newlow: '신저가', etf: 'ETF' };
const WD = ['일', '월', '화', '수', '목', '금', '토'];
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safe = (t) => t.replace(/[^A-Za-z0-9]/g, '_');

let INDEX = null;
let state = { market: 'jp', view: 'newhigh', date: null };
let current = { day: null, items: new Map() };
let chart = null;
const jcache = new Map();

async function getJSON(path, fresh = false) {
  if (!fresh && jcache.has(path)) return jcache.get(path);
  const r = await fetch(`${path}?v=${encodeURIComponent(INDEX?.updated || Date.now())}`, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  const j = await r.json();
  jcache.set(path, j);
  return j;
}

const fmtDate = (d) => { const [y, m, dd] = d.split('-'); return `${y}.${m}.${dd}(${WD[new Date(d + 'T00:00:00').getDay()]})`; };
const fp = (v, d = 1) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(d)}%`);
const cls = (v) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');
const fnum = (v) => (v == null ? '–' : v.toLocaleString('ko-KR', { maximumFractionDigits: v >= 1000 ? 0 : 2 }));
const cat = (it) => (it.industry && it.industry !== it.sector ? `${it.sector} › ${it.industry}` : it.sector);
const code = (t) => t.replace(/\.T$/, '');

function parseHash() {
  const [m, v, d] = location.hash.replace(/^#/, '').split('/');
  if (MARKETS[m]) state.market = m;
  if (VIEWS[v]) state.view = v;
  state.date = /^\d{4}-\d{2}-\d{2}$/.test(d || '') ? d : null;
}
const go = (p) => { location.hash = `${p.market ?? state.market}/${p.view ?? state.view}/${p.date ?? state.date ?? ''}`; };

// 업종별 그룹 묶기 (그룹 순서 = 그룹 내 최고 등락률 순)
function groups(items, desc) {
  const sorter = (a, b) => (desc ? (b.d1 ?? -1e9) - (a.d1 ?? -1e9) : (a.d1 ?? 1e9) - (b.d1 ?? 1e9));
  const m = new Map();
  for (const it of items) { const k = cat(it); if (!m.has(k)) m.set(k, []); m.get(k).push(it); }
  return [...m.entries()].map(([k, arr]) => ({ k, arr: arr.sort(sorter) })).sort((a, b) => sorter(a.arr[0], b.arr[0]));
}

const colsHTML = () => '<div class="cols"><span>종목</span><span>금일</span><span>5일</span><span>1달</span></div>';
function rowHTML(it, label) {
  const sub = state.market === 'jp' ? `${code(it.ticker)} ${it.name_local || ''}` : it.ticker;
  return `<button class="row" data-t="${esc(it.ticker)}">
    <span class="nm"><b>${esc(label ?? it.name)}${it.small ? '<span class="tag">소형주</span>' : ''}</b><small>${esc(label ? it.ticker : sub)}</small></span>
    <span class="p ${cls(it.d1)}">${fp(it.d1)}</span>
    <span class="p sm ${cls(it.d5)}">${fp(it.d5)}</span>
    <span class="p sm ${cls(it.m1)}">${fp(it.m1)}</span></button>`;
}
function sectionHTML(title, items, desc) {
  const body = items.length
    ? colsHTML() + groups(items, desc).map((g) => `<div class="group"><div class="ghead"><span>(${esc(g.k)})</span><span>${g.arr.length}</span></div>${g.arr.map((i) => rowHTML(i)).join('')}</div>`).join('')
    : '<div class="empty">해당 종목 없음</div>';
  return `<section><h2>${title} <span class="n">${items.length}</span></h2>${body}</section>`;
}

function summaryText(day) {
  const mk = MARKETS[state.market];
  const L = [`${mk.flag} ${mk.name} ${VIEWS[state.view]} · ${fmtDate(day.date)}`];
  const block = (title, items, desc) => {
    L.push('', `${title} ${items.length}`);
    for (const g of groups(items, desc)) L.push(`(${g.k}) ` + g.arr.map((i) => `${i.name}${i.small ? ' [소형주]' : ''} ${fp(i.d1)}`).join(', '));
  };
  if (state.view === 'newhigh') {
    L.push(day.criteria.high);
    block('🏆 역대 신고가', day.newhigh.ath, true);
    block('📈 52주 신고가 (역대 제외)', day.newhigh.w52, true);
  } else if (state.view === 'newlow') {
    L.push(day.criteria.low);
    block('🧊 역대 신저가', day.newlow.atl, false);
    block('📉 52주 신저가 (역대 제외)', day.newlow.w52, false);
  } else {
    L.push('');
    for (const e of day.etfs) L.push(`${e.ticker} (${e.label}) 금일 ${fp(e.d1)}, 최근 5일 ${fp(e.d5)}, 최근 1달 ${fp(e.m1)}`);
  }
  L.push('', `🔗 ${location.href}`);
  return L.join('\n');
}

async function render() {
  parseHash();
  document.querySelectorAll('#markets button').forEach((b) => b.classList.toggle('on', b.dataset.m === state.market));
  document.querySelectorAll('#views button').forEach((b) => b.classList.toggle('on', b.dataset.v === state.view));
  const main = $('#main');
  const dates = INDEX?.[state.market] || [];
  const sel = $('#date');
  if (!dates.length) {
    sel.innerHTML = ''; $('#prev').disabled = $('#next').disabled = true;
    main.innerHTML = '<div class="empty">아직 데이터가 없습니다. GitHub Actions에서 <b>Daily update</b> 워크플로를 한 번 실행해 주세요.</div>';
    return;
  }
  const date = dates.includes(state.date) ? state.date : dates[0];
  sel.innerHTML = dates.map((d) => `<option value="${d}" ${d === date ? 'selected' : ''}>${fmtDate(d)}</option>`).join('');
  const i = dates.indexOf(date);
  $('#prev').disabled = i >= dates.length - 1;
  $('#next').disabled = i <= 0;

  let day;
  try { day = await getJSON(`data/${state.market}/${date}.json`); }
  catch (e) { main.innerHTML = `<div class="empty">데이터를 불러오지 못했습니다 (${esc(e.message)})</div>`; return; }
  current.day = day; current.items = new Map();

  const mk = MARKETS[state.market];
  let html = `<div class="title"><h1>${mk.flag} ${mk.name} ${VIEWS[state.view]} · ${fmtDate(day.date)}</h1><button class="copy" id="copy">텍스트 복사</button></div>`;
  if (state.view === 'newhigh') {
    [...day.newhigh.ath, ...day.newhigh.w52].forEach((it) => current.items.set(it.ticker, { ...it, kind: 'high' }));
    html += `<p class="sub muted small">${esc(day.criteria.high)} · 공통 대분류 › 세부 업종 · 종목을 누르면 1년 차트</p>`;
    html += sectionHTML('🏆 역대 신고가', day.newhigh.ath, true);
    html += sectionHTML('📈 52주 신고가 <span class="muted small">(역대 제외)</span>', day.newhigh.w52, true);
  } else if (state.view === 'newlow') {
    [...day.newlow.atl, ...day.newlow.w52].forEach((it) => current.items.set(it.ticker, { ...it, kind: 'low' }));
    html += `<p class="sub muted small">${esc(day.criteria.low)} · 공통 대분류 › 세부 업종 · 종목을 누르면 1년 차트</p>`;
    html += sectionHTML('🧊 역대 신저가', day.newlow.atl, false);
    html += sectionHTML('📉 52주 신저가 <span class="muted small">(역대 제외)</span>', day.newlow.w52, false);
  } else {
    day.etfs.forEach((e) => current.items.set(e.ticker, { ...e, name: e.label, kind: 'etf' }));
    html += '<p class="sub muted small">config/etfs.json 에서 종목을 바꿀 수 있습니다 · 누르면 1년 차트</p>';
    html += `<section>${colsHTML()}<div class="group">${day.etfs.map((e) => rowHTML(e, e.label)).join('')}</div></section>`;
  }
  html += `<p class="muted small">집계 대상 ${day.priced?.toLocaleString()} / ${day.universe?.toLocaleString()}종목 · 생성 ${new Date(day.generated_at).toLocaleString('ko-KR')}</p>`;
  main.innerHTML = html;

  $('#copy').onclick = async () => {
    try { await navigator.clipboard.writeText(summaryText(day)); $('#copy').textContent = '복사됨 ✓'; }
    catch { $('#copy').textContent = '복사 실패'; }
    setTimeout(() => { const b = $('#copy'); if (b) b.textContent = '텍스트 복사'; }, 1500);
  };
}

// ------------------------------------------------------------ 차트 모달
async function openChart(t) {
  const it = current.items.get(t);
  if (!it) return;
  const modal = $('#modal');
  $('#mtitle').innerHTML = `${esc(it.name)}${it.small ? '<span class="tag">소형주</span>' : ''}`;
  $('#msub').textContent = [state.market === 'jp' ? code(t) : t, it.name_local, it.sector ? cat(it) : ''].filter(Boolean).join(' · ');
  const refLabel = it.kind === 'low' ? '직전 52주 저가' : '직전 52주 고가';
  $('#mstats').innerHTML = [
    `<span>종가 <b>${fnum(it.close)}</b></span>`,
    `<span>금일 <b class="${cls(it.d1)}">${fp(it.d1, 2)}</b></span>`,
    `<span>5일 <b class="${cls(it.d5)}">${fp(it.d5, 2)}</b></span>`,
    `<span>1달 <b class="${cls(it.m1)}">${fp(it.m1, 2)}</b></span>`,
    it.ref != null ? `<span class="muted">${refLabel} ${fnum(it.ref)}</span>` : '',
    it.ath ? `<span class="muted">${it.kind === 'low' ? '역대 신저가' : '역대 신고가'}${it.since ? ` (${it.since.slice(0, 4)}년 이후 데이터 기준)` : ''}</span>` : '',
    it.from_high != null ? `<span class="muted">52주 고점 대비 ${fp(it.from_high)}</span>` : '',
  ].join('');
  const yq = `https://finance.yahoo.com/quote/${encodeURIComponent(t)}`;
  $('#mlinks').innerHTML = `<a href="${yq}" target="_blank" rel="noopener">Yahoo Finance ↗</a>` +
    (state.market === 'jp' ? `<a href="https://kabutan.jp/stock/?code=${encodeURIComponent(code(t))}" target="_blank" rel="noopener">株探 ↗</a>` : `<a href="https://finviz.com/quote.ashx?t=${encodeURIComponent(t)}" target="_blank" rel="noopener">Finviz ↗</a>`);
  if (!modal.open) modal.showModal();
  const box = $('#chart');
  if (chart) { chart.remove(); chart = null; }
  box.innerHTML = '<p class="muted">차트 불러오는 중…</p>';

  let data;
  try { data = await getJSON(`data/charts/${state.market}/${safe(t)}.json`); }
  catch { box.innerHTML = '<p class="muted">차트 데이터가 없습니다.</p>'; return; }
  if (!window.LightweightCharts) { box.innerHTML = '<p class="muted">차트 라이브러리를 불러오지 못했습니다.</p>'; return; }
  box.innerHTML = '';

  const css = getComputedStyle(document.documentElement);
  const up = css.getPropertyValue('--up').trim(), down = css.getPropertyValue('--down').trim();
  const fg = css.getPropertyValue('--muted').trim(), line = css.getPropertyValue('--line').trim();
  chart = LightweightCharts.createChart(box, {
    autoSize: true,
    layout: { background: { color: 'transparent' }, textColor: fg },
    grid: { vertLines: { color: line }, horzLines: { color: line } },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false },
    localization: { locale: 'ko-KR' },
  });
  const cs = chart.addCandlestickSeries({ upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, borderVisible: false });
  cs.setData(data.bars.map((b) => ({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] })));
  const vs = chart.addHistogramSeries({ priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false });
  chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  vs.setData(data.bars.map((b) => ({ time: b[0], value: b[5], color: (b[4] >= b[1] ? up : down) + '66' })));
  if (it.ref != null && it.kind !== 'etf') cs.createPriceLine({ price: it.ref, color: fg, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: refLabel });
  const day = current.day?.date;
  if (day && it.kind !== 'etf' && data.bars.some((b) => b[0] === day)) {
    cs.setMarkers([{ time: day, position: it.kind === 'low' ? 'belowBar' : 'aboveBar', color: it.kind === 'low' ? down : up,
      shape: it.kind === 'low' ? 'arrowUp' : 'arrowDown', text: it.kind === 'low' ? '신저가' : '신고가' }]);
  }
  chart.timeScale().fitContent();
  const last = data.bars.at(-1)?.[0];
  document.querySelectorAll('#ranges button').forEach((b) => {
    b.classList.toggle('on', b.dataset.r === '12');
    b.onclick = () => {
      document.querySelectorAll('#ranges button').forEach((x) => x.classList.toggle('on', x === b));
      if (b.dataset.r === '12') return chart.timeScale().fitContent();
      const from = new Date(last + 'T00:00:00'); from.setMonth(from.getMonth() - Number(b.dataset.r));
      chart.timeScale().setVisibleRange({ from: from.toISOString().slice(0, 10), to: last });
    };
  });
}

function closeChart() { const m = $('#modal'); if (m.open) m.close(); }

// ------------------------------------------------------------ 시작
async function init() {
  $('#markets').onclick = (e) => { const m = e.target.closest('button')?.dataset.m; if (m) go({ market: m, date: '' }); };
  $('#views').onclick = (e) => { const v = e.target.closest('button')?.dataset.v; if (v) go({ view: v }); };
  $('#date').onchange = (e) => go({ date: e.target.value });
  const step = (k) => { const ds = INDEX?.[state.market] || []; const i = ds.indexOf($('#date').value); const d = ds[i + k]; if (d) go({ date: d }); };
  $('#prev').onclick = () => step(1);
  $('#next').onclick = () => step(-1);
  $('#main').onclick = (e) => { const r = e.target.closest('.row'); if (r) openChart(r.dataset.t); };
  $('#mclose').onclick = closeChart;
  $('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') closeChart(); });
  $('#modal').addEventListener('close', () => { if (chart) { chart.remove(); chart = null; } });
  window.addEventListener('hashchange', render);
  try { INDEX = await (await fetch(`data/index.json?t=${Date.now()}`, { cache: 'no-cache' })).json(); }
  catch { INDEX = { jp: [], us: [] }; }
  render();
}
init();
