#!/usr/bin/env python3
"""매일 실행: 시장별 신고가 · 일간/주간 상승률 상위, ETF, 거시 지표 → docs/data/ 에 JSON 저장.

사용법:  python scripts/update.py --market us,etf,macro_us   (쉼표로 여러 개)
대상: us, kr, jp, etf, macro_us, macro_kr, all
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from universe import load_universe  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
CACHE = ROOT / "cache"
SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text("utf-8"))
ETFS = json.loads((ROOT / "config" / "etfs.json").read_text("utf-8"))
COLS = ["Open", "High", "Low", "Close", "Volume"]
LEVERAGED = re.compile(r"\b(\d(\.\d+)?x|ultra|ultrapro|ultrashort|leveraged|inverse|bear|daily|bull|2x|3x|-1x|-2x|-3x)\b|\bshort\b(?![ -](term|duration|maturity))", re.I)


def log(*a):
    print(*a, flush=True)


def safe(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", t)


def pct(a, b):
    if a is None or b is None or pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return round((float(a) / float(b) - 1) * 100, 2)


def num(x):
    if x is None or pd.isna(x):
        return None
    x = float(x)
    return round(x, 2) if abs(x) >= 1 else round(x, 4)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, obj, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, **({"separators": (",", ":")} if compact else {"indent": 1})), "utf-8")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------- 시세 받기
def _clean(df):
    df = df[[c for c in COLS if c in df.columns]].copy()
    df = df.dropna(subset=["Close"])
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


def _pick(raw, t):
    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        if t in raw.columns.get_level_values(0):
            sub = raw[t]
        elif t in raw.columns.get_level_values(1):
            sub = raw.xs(t, axis=1, level=1)
        else:
            return None
    else:
        sub = raw
    sub = sub.dropna(how="all")
    if sub.empty or "Close" not in sub.columns:
        return None
    return _clean(sub)


def download(tickers, period, interval="1d"):
    """yfinance 일괄 다운로드 (묶음 단위, 빠진 종목 최대 2회 재시도). {ticker: DataFrame}"""
    import yfinance as yf

    out, todo = {}, list(dict.fromkeys(tickers))
    size = SETTINGS["chunk_size"]
    for rnd in range(3):
        missing = []
        for i in range(0, len(todo), size):
            part = todo[i:i + size]
            try:
                raw = yf.download(part, period=period, interval=interval, group_by="ticker",
                                  auto_adjust=False, actions=False, threads=True, progress=False)
            except Exception as e:  # noqa: BLE001
                log("  다운로드 오류:", e)
                missing += part
                time.sleep(20)
                continue
            for t in part:
                sub = _pick(raw, t)
                if sub is None or sub.empty:
                    missing.append(t)
                else:
                    out[t] = sub
            time.sleep(SETTINGS["sleep_sec"])
        log(f"  [{period}] {len(out)}/{len(set(tickers))} (라운드 {rnd + 1})")
        if not missing or rnd == 2 or len(missing) == len(todo) and rnd > 0:
            break
        todo = missing
        time.sleep(45)
    return out


# ---------------------------------------------------------------- 계산
def returns(df):
    """d1 = 전일 대비, w1 = 이번 주 수익률 (지난주 마지막 종가 대비)."""
    c = df["Close"].dropna()
    last, d = c.iloc[-1], c.index[-1]
    monday = d - pd.Timedelta(days=d.weekday())
    prev_week = c[c.index < monday]
    prev2 = c[c.index < monday - pd.Timedelta(days=7)]
    return {
        "close": num(last),
        "d1": pct(last, c.iloc[-2]) if len(c) > 1 else None,
        "w1": pct(last, prev_week.iloc[-1]) if len(prev_week) else None,
        "w1_prev": pct(prev_week.iloc[-1], prev2.iloc[-1]) if len(prev_week) and len(prev2) else None,
    }


# ---------------------------------------------------------------- 시가총액 구간
CAP_ORDER = ["L", "M", "S", "U"]  # 대형 ≥$10B, 중형 $1B~10B, 소형 $0.1B~1B, U=시총 미확인


def quote_batch(tickers):
    """Yahoo 일괄 시세(100개씩)로 시가총액·통화·PER을 받는다. {ticker: {...}}"""
    from yfinance.data import YfData
    yd, out = YfData(), {}
    tickers = list(dict.fromkeys(tickers))
    for i in range(0, len(tickers), 100):
        part = tickers[i:i + 100]
        for attempt in range(3):
            try:
                r = yd.get_raw_json("https://query1.finance.yahoo.com/v7/finance/quote",
                                    params={"symbols": ",".join(part), "fields": "marketCap,currency,trailingPE,regularMarketPrice,shortName,longName,netAssets,firstTradeDateMilliseconds"})
                for x in r["quoteResponse"]["result"]:
                    out[x["symbol"]] = {"mcap": x.get("marketCap"), "cur": x.get("currency"),
                                        "pe": x.get("trailingPE"), "px": x.get("regularMarketPrice"),
                                        "name": x.get("shortName") or x.get("longName"),
                                        "aum": x.get("netAssets"), "first": x.get("firstTradeDateMilliseconds")}
                break
            except Exception as e:  # noqa: BLE001
                log("  시총 조회 오류:", repr(e)[:120])
                time.sleep(10 * (attempt + 1))
        time.sleep(0.5)
    return out


def market_caps(market, tickers):
    """종목별 (현지통화 시총, 달러 환산 시총). 실패 시 직전 캐시 사용."""
    cpath = CACHE / f"mcap_{market}.json"
    cache = read_json(cpath, {})
    fx_sym = {"jp": "JPY=X", "tw": "TWD=X"}.get(market)
    q = quote_batch(list(tickers) + ([fx_sym] if fx_sym else []))
    fx = (q.get(fx_sym, {}).get("px") if fx_sym else 1.0) or cache.get("_fx")
    if fx:
        cache["_fx"] = fx
    for t in tickers:
        m = q.get(t, {}).get("mcap")
        if m and fx:
            cache[t] = [m, m / fx]
    write_json(cpath, cache)
    log(f"  시총 {sum(1 for t in tickers if t in cache)}/{len(tickers)} (환율 {fx})")
    if market in ("jp", "tw"):  # 영문명도 같이 저장
        npath = CACHE / "names.json"
        names = read_json(npath, {})
        names.update({t: q[t]["name"].strip() for t in tickers if q.get(t, {}).get("name")})
        write_json(npath, dict(sorted(names.items())))
    return {t: cache[t] for t in tickers if t in cache}, {t: q[t].get("pe") for t in q if t in tickers}


def cap_bucket(usd):
    big, mid, small = SETTINGS["cap_buckets_usd"]
    if not usd:
        return "U"
    return "L" if usd >= big else "M" if usd >= mid else "S" if usd >= small else None


def top_by_cap(rows, key, n):
    out = []
    for b in CAP_ORDER:
        out += top_n([r for r in rows if r.get("cap", "U") == b], key, n)
    return out


ETF_CRIT = "aum1조-6m-h10"


def weekly_top(market, rows, trade_date, n):
    """주간 상승률 상위는 금요일(주 마지막 거래일) 데이터로만 새로 집계하고, 그 외 날은 직전 목록을 유지."""
    monday = trade_date - pd.Timedelta(days=trade_date.weekday())
    label = f"{monday:%Y-%m-%d}~{monday + pd.Timedelta(days=4):%Y-%m-%d}"
    by = top_by_cap if market in ("us", "jp", "tw") else top_n
    if trade_date.weekday() == 4:
        return by(rows, "w1", n), label
    ds = trade_date.strftime("%Y-%m-%d")
    for d in read_json(DATA / "index.json", {}).get(market, []):
        if d >= ds:
            continue
        prev = read_json(DATA / market / f"{d}.json", {})
        ok_caps = market not in ("us", "jp", "tw") or all("cap" in r for r in prev.get("top_w1", []))
        if market == "etf" and prev.get("w1_crit") != ETF_CRIT:  # 선정 기준이 바뀌면 새로 집계
            ok_caps = False
        if prev.get("top_n", 50) != n:  # 목록 개수가 바뀌면 새로 집계
            ok_caps = False
        if prev.get("w1_week") and prev.get("top_w1") and ok_caps:
            return prev["top_w1"], prev["w1_week"]
    # 직전 목록이 없으면 지난주(완료된 주) 수익률로 집계
    lm = monday - pd.Timedelta(days=7)
    last = [{**r, "w1": r["w1_prev"]} for r in rows if r.get("w1_prev") is not None]
    return by(last, "w1", n), f"{lm:%Y-%m-%d}~{lm + pd.Timedelta(days=4):%Y-%m-%d}"


def momentum(c, idx_c=None):
    """최근 1주(5거래일)·1달(21거래일) 수익률, 시장 대비 초과수익(%p), 50·200일선 위치."""
    def r(x, n):
        return float(x.iloc[-1] / x.iloc[-1 - n] - 1) * 100 if len(x) > n else None
    out = {"r1w": r(c, 5), "r1m": r(c, 21)}
    ir1w, ir1m = (r(idx_c, 5), r(idx_c, 21)) if idx_c is not None else (0.0, 0.0)
    out["rel1w"] = round(out["r1w"] - ir1w, 2) if out["r1w"] is not None and ir1w is not None else None
    out["rel1m"] = round(out["r1m"] - ir1m, 2) if out["r1m"] is not None and ir1m is not None else None
    out["r1w"] = round(out["r1w"], 2) if out["r1w"] is not None else None
    out["r1m"] = round(out["r1m"], 2) if out["r1m"] is not None else None
    px = c.iloc[-1]
    out["above50"] = bool(px > c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else None
    out["above200"] = bool(px > c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    return out


def is_rising(m):
    """최근 시장 대비 강세: 1주·1달 모두 시장보다 강하고, 둘 중 하나는 뚜렷하게(+2%p 이상) 강할 것."""
    a, b = m.get("rel1w"), m.get("rel1m")
    return a is not None and b is not None and a > 0 and b > 0 and (a >= 2 or b >= 2)


def ma_signals(df, cfg):
    """이평선 신호. 반환: [(type, 짧은표시, 설명)]
    up=일봉 상향돌파, touch=일봉 근접(고가가 이평선 근처까지, 종가는 아래), gc/dc=골든·데드크로스, conv=이평선 수렴."""
    d = df.dropna(subset=["Open", "High", "Low", "Close"])
    c, h, o = d["Close"], d["High"], d["Open"]
    periods = sorted(set(cfg["price"]) | {x for p in cfg["pairs"] for x in p})
    ma = {n: c.rolling(n).mean() for n in periods}
    out = []
    tp = cfg["touch_pct"] / 100
    for n in cfg["price"]:
        m = ma[n]
        if len(m) < 2 or pd.isna(m.iloc[-1]) or pd.isna(m.iloc[-2]):
            continue
        if c.iloc[-1] > m.iloc[-1] and c.iloc[-2] <= m.iloc[-2]:
            out.append(("up", f"{n}일선↑", f"종가가 {n}일선 상향돌파"))
        elif c.iloc[-1] < m.iloc[-1] and h.iloc[-1] >= m.iloc[-1] * (1 - tp):
            tail = "음봉으로 이평선 아래 마감" if c.iloc[-1] < o.iloc[-1] else "이평선 아래에서 마감"
            out.append(("touch", f"{n}일선 근접", f"고가가 {n}일선 {cfg['touch_pct']}% 이내까지 올라온 뒤 {tail}"))
    near = cfg["near_pct"] / 100
    for a, b in cfg["pairs"]:
        sa, lb = ma[a], ma[b]
        if len(lb) < 7 or pd.isna(lb.iloc[-6]) or pd.isna(sa.iloc[-6]):
            continue
        if sa.iloc[-1] > lb.iloc[-1] and sa.iloc[-2] <= lb.iloc[-2]:
            out.append(("gc", f"{a}/{b} GC", f"{a}일선이 {b}일선 상향돌파 (골든크로스)"))
        elif sa.iloc[-1] < lb.iloc[-1] and sa.iloc[-2] >= lb.iloc[-2]:
            out.append(("dc", f"{a}/{b} DC", f"{a}일선이 {b}일선 하향돌파 (데드크로스)"))
        else:
            gap = abs(sa.iloc[-1] - lb.iloc[-1]) / lb.iloc[-1]
            gap5 = abs(sa.iloc[-6] - lb.iloc[-6]) / lb.iloc[-6]
            if gap <= near and gap < gap5:
                side = "골든크로스 접근" if sa.iloc[-1] < lb.iloc[-1] else "데드크로스 접근"
                out.append(("conv", f"{a}/{b} {gap * 100:.1f}%", f"{a}일선과 {b}일선 차이 {gap * 100:.1f}% (5일 전 {gap5 * 100:.1f}%) · {side}"))
    return out


def is_new_high(df):
    """당일 52주 신고가 여부. 반환: 직전 52주 고가 또는 None"""
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < SETTINGS["min_history_days"] + 1:
        return None
    lb, r = SETTINGS["lookback_days"], SETTINGS["rules"]
    t, p = df.iloc[-1], df.iloc[-2]
    hi = df.iloc[-(lb + 1):-1]["High"].max()
    if (t.High > hi and (not r["high_require_up"] or t.Close > p.Close)
            and (not r["high_require_bullish"] or t.Close > t.Open)):
        return hi
    return None


def ath_flags(tickers, hist, trade_date):
    if not tickers:
        return {}
    full = download(tickers, "max")
    out = {}
    for t in tickers:
        f = full.get(t)
        if f is None or f.empty:
            continue
        prior = f[f.index < trade_date]
        if len(prior):
            out[t] = (bool(hist[t].iloc[-1].High > prior["High"].max()), prior.index[0].strftime("%Y-%m-%d"))
    return out


def english_names(tickers):
    cpath = CACHE / "names.json"
    cache = read_json(cpath, {})
    need = [t for t in tickers if t not in cache]
    if need:
        import yfinance as yf
        for t in need:
            try:
                info = yf.Ticker(t).info
                n = info.get("shortName") or info.get("longName")
                if n:
                    cache[t] = n.strip()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.4)
        write_json(cpath, dict(sorted(cache.items())))
    return cache


def bars_of(df, since=None):
    d = df if since is None else df[df.index >= since]
    return [[i.strftime("%Y-%m-%d"), num(r.Open), num(r.High), num(r.Low), num(r.Close),
             0 if pd.isna(r.Volume) else int(r.Volume)] for i, r in d.iterrows()
            if not any(pd.isna(v) for v in (r.Open, r.High, r.Low, r.Close))]


def write_chart(market, t, name, df, wk=None, mas=None):
    cut = df.index[-1] - pd.DateOffset(days=SETTINGS["chart_days"])
    obj = {"ticker": t, "name": name, "updated": df.index[-1].strftime("%Y-%m-%d"), "bars": bars_of(df, cut)}
    if mas:  # 이평선(전체 기간으로 계산 후 차트 구간만)
        d = df.dropna(subset=["Open", "High", "Low", "Close"])
        keep = d.index >= cut
        obj["ma"] = {str(n): [None if pd.isna(v) else num(v) for v in d["Close"].rolling(n).mean()[keep]] for n in mas}
    if wk is not None and len(wk):
        obj["weekly"] = bars_of(wk)
    write_json(DATA / "charts" / market / f"{safe(t)}.json", obj, compact=True)


def weekly(tickers):
    return download(sorted(tickers), f"{SETTINGS['weekly_years']}y", "1wk") if tickers else {}


def rs_ratings(hist, trade_date):
    """IBD 방식 RS: 최근 3·6·9·12개월 수익률 가중합(최근 3개월 2배)의 백분위 1~99."""
    sc = {}
    for t, df in hist.items():
        c = df["Close"].dropna()
        if df.index[-1] != trade_date or len(c) < 253:
            continue
        r = lambda n: c.iloc[-1] / c.iloc[-1 - n] - 1  # noqa: E731
        sc[t] = 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)
    if not sc:
        return {}
    s = pd.Series(sc).rank(pct=True)
    return {t: int(max(1, min(99, round(v * 99)))) for t, v in s.items()}


def fundamentals(tickers, closes):
    """시가총액·PER·PSR. 주식 수·EPS·매출은 7일간 캐시, 가격은 당일 종가로 계산."""
    import yfinance as yf
    cpath = CACHE / "fundamentals.json"
    cache = read_json(cpath, {})
    today = dt.date.today()
    cache = {t: v for t, v in cache.items() if any(v.get(k) for k in ("shares", "eps", "rev", "mcap"))}  # 빈 기록 제거
    fresh = lambda t: t in cache and (today - dt.date.fromisoformat(cache[t]["at"])).days < 7  # noqa: E731
    todo = [t for t in tickers if not fresh(t)][:SETTINGS.get("info_per_run", 150)]
    fails = 0
    for t in todo:
        if fails >= 8:  # 연속 실패면 오늘은 중단 (다음 실행에서 이어서)
            log("  종목 정보 요청이 막혀 중단 — 다음 실행에서 이어서 받습니다")
            break
        got = False
        for attempt in range(2):
            try:
                i = yf.Ticker(t).info or {}
                rec = {"at": today.isoformat(), "shares": i.get("sharesOutstanding") or i.get("impliedSharesOutstanding"),
                       "eps": i.get("trailingEps"), "rev": i.get("totalRevenue"), "mcap": i.get("marketCap")}
                if any(rec[k] for k in ("shares", "eps", "rev", "mcap")):  # 빈 응답은 저장하지 않음
                    cache[t] = rec
                    got = True
                break
            except Exception:  # noqa: BLE001
                time.sleep(5 * (attempt + 1))
        fails = 0 if got else fails + 1
        time.sleep(0.35)
    write_json(cpath, cache)
    out = {}
    for t in tickers:
        f, px = cache.get(t), closes.get(t)
        if not f or px is None:
            continue
        mcap = f["shares"] * px if f.get("shares") else f.get("mcap")
        out[t] = {"mcap": mcap,
                  "per": round(px / f["eps"], 1) if f.get("eps") and f["eps"] > 0 else None,
                  "psr": round(mcap / f["rev"], 2) if mcap and f.get("rev") and f["rev"] > 0 else None}
    return out


def trade_date_of(hist):
    return pd.Series([df.index[-1] for df in hist.values()]).mode().max()


def add_index(market, ds):
    ipath = DATA / "index.json"
    idx = read_json(ipath, {})
    idx[market] = sorted(set(idx.get(market, [])) | {ds}, reverse=True)
    idx["updated"] = now_iso()
    write_json(ipath, idx)


def top_n(rows, key, n):
    rows = [r for r in rows if r.get(key) is not None]
    return sorted(rows, key=lambda r: -r[key])[:n]


# ---------------------------------------------------------------- 주식 (미국/한국/일본)
def run_stocks(market):
    log(f"===== {market.upper()} 주식 =====")
    uni = load_universe(market, CACHE, SETTINGS.get("us_min_mcap", 3e8))
    caps, pes = ({}, {})
    if market in ("jp", "tw"):  # 대량 다운로드 전에 시총을 먼저 받는다
        caps, pes = market_caps(market, list(uni))
    elif market == "us":
        caps = {t: [m["mcap"], m["mcap"]] for t, m in uni.items() if m.get("mcap")}
    hist = download(list(uni), "18mo")
    if not hist:
        raise RuntimeError("시세를 하나도 받지 못했습니다")
    bench = {"us": "^GSPC", "jp": "^N225", "tw": "^TWII", "kr": "^KS11"}[market]
    bdf = download([bench], "13mo").get(bench)
    bclose = bdf["Close"].dropna() if bdf is not None else None
    trade_date = trade_date_of(hist)
    ds = trade_date.strftime("%Y-%m-%d")
    log(f"기준일 {ds} / 시세 {len(hist)}종목")

    rows, highs = [], []
    for t, df in hist.items():
        if df.index[-1] != trade_date or len(df) < 7:
            continue
        if df["Volume"].iloc[-1] == 0:
            continue
        pc = df["Close"].iloc[-2]
        if pc < 1 and df["Close"].iloc[-1] / pc > 4:  # 미반영 액면병합으로 보이는 급등 제외
            continue
        m = uni[t]
        row = {"ticker": t, "name": m["name"], "name_local": m.get("name_local", ""),
               "sector": m["sector"], "industry": m["industry"], "small": bool(m.get("small")), **returns(df)}
        if market in ("us", "jp", "tw"):
            c = caps.get(t)
            row["cap"] = cap_bucket(c[1] if c else None)
            if row["cap"] is None:  # 시총 1억달러 미만은 제외
                continue
            if c:
                row["mcap"], row["mcap_usd"] = c[0], round(c[1])
            if pes.get(t):
                row["per"] = round(pes[t], 1)
        if market in ("us", "jp", "tw"):
            row.update(momentum(df["Close"].dropna(), bclose))
        mcfg = SETTINGS.get("ma_signals", {}).get(market)
        if mcfg:
            sg = ma_signals(df, mcfg)
            if sg:
                row["sigs"] = [{"t": t, "s": a, "d": b} for t, a, b in sg]
                row["turnover"] = round(float(df["Close"].iloc[-1] * df["Volume"].iloc[-1]))
        if market == "kr":  # 거래량: 당일 vs 직전 5거래일 평균
            v = df["Volume"]
            avg5 = v.iloc[-6:-1].mean() if len(v) >= 6 else None
            if avg5 and avg5 > 0:
                row["vol"], row["vol5"] = int(v.iloc[-1]), int(avg5)
                row["vsurge"] = round((v.iloc[-1] / avg5 - 1) * 100, 1)
        rows.append(row)
        ref = is_new_high(df)
        if ref is not None:
            highs.append({**row, "ref": num(ref)})

    n = SETTINGS.get("top_n_by_market", {}).get(market, SETTINGS["top_n"])
    top_d1 = top_by_cap(rows, "d1", n) if market in ("us", "jp", "tw") else top_n(rows, "d1", n)
    top_w1, w1_week = weekly_top(market, rows, trade_date, n)
    masig = [r for r in rows if r.get("sigs")]
    masig.sort(key=lambda r: -(r.get("mcap_usd") or r.get("turnover") or 0))
    if masig:
        log(f"이평선 신호 {len(masig)}종목")
    vsurge = []
    if market == "kr":
        vsurge = sorted([r for r in rows if r.get("vsurge") is not None and r["vsurge"] >= SETTINGS.get("vsurge_min_pct", 30)],
                        key=lambda r: -r["vsurge"])
        log(f"거래량 급증 {len(vsurge)}종목")
    rising = []
    if market in ("us", "jp", "tw"):
        for r in rows:
            if is_rising(r):
                r["score"] = round(r["rel1w"] + r["rel1m"], 2)
        rising = top_by_cap([r for r in rows if "score" in r and is_rising(r)], "score", n)
    flags = ath_flags([h["ticker"] for h in highs], hist, trade_date)
    for h in highs:
        h["ath"], h["since"] = flags.get(h["ticker"], (False, None))
    highs.sort(key=lambda r: -(r["d1"] or 0))
    log(f"신고가 {len(highs)} (역대 {sum(h['ath'] for h in highs)})")

    # 이평선 신호 종목은 신호 종류별로 앞쪽(시총·거래대금 큰 순) 일부만 차트 파일을 만든다 (저장소 용량)
    sig_chart = set()
    for typ in ("up", "touch", "gc", "dc", "conv"):
        sig_chart |= {r["ticker"] for r in [x for x in masig if any(g["t"] == typ for g in x["sigs"])][:SETTINGS.get("ma_signal_charts", 300) // 3]}
    for r in masig:
        r["chart"] = r["ticker"] in sig_chart
    shown = {r["ticker"] for r in highs + top_d1 + top_w1 + rising + vsurge if r["ticker"] in hist} | sig_chart
    every = highs + top_d1 + top_w1 + rising + vsurge + [r for r in masig if r["chart"]]
    if market in ("jp", "tw"):  # 영문명은 캐시에 있는 것만 (새로 받는 건 meta 단계)
        names = read_json(CACHE / "names.json", {})
        for r in every:
            r["name"] = names.get(r["ticker"], r["name"])
    if market == "us":
        qq = quote_batch(sorted(shown))
        for r in every:
            if qq.get(r["ticker"], {}).get("pe"):
                r["per"] = round(qq[r["ticker"]]["pe"], 1)
    if market != "kr":
        rs = rs_ratings(hist, trade_date)
        for r in every:
            r["rs"] = rs.get(r["ticker"])
    wk = weekly(shown)
    mcfg = SETTINGS.get("ma_signals", {}).get(market)
    mas = sorted(set(mcfg["price"]) | {x for p in mcfg["pairs"] for x in p}) if mcfg else None
    for t in shown:
        write_chart(market, t, uni[t]["name"], hist[t], wk.get(t), mas if t in sig_chart else None)

    write_json(DATA / market / f"{ds}.json", {
        "market": market, "date": ds, "generated_at": now_iso(),
        "universe": len(uni), "priced": len(rows), "criteria": criteria_text(),
        "newhigh": highs, "top_d1": top_d1, "top_w1": top_w1, "w1_week": w1_week, "rising": rising, "top_n": n, "vsurge": vsurge, "masig": masig,
        "masig_cfg": SETTINGS.get("ma_signals", {}).get(market),
        "bench": bench,
    })
    add_index(market, ds)
    log(f"저장 완료: docs/data/{market}/{ds}.json")


def criteria_text():
    r = SETTINGS["rules"]
    hi = "·".join([x for x, on in (("상승", r["high_require_up"]), ("양봉", r["high_require_bullish"])) if on])
    return f"{hi + ' 마감 · ' if hi else ''}장중 52주({SETTINGS['lookback_days']}거래일) 고가 돌파"


# ---------------------------------------------------------------- ETF
def etf_holdings(t):
    import yfinance as yf
    for attempt in range(3):
        try:
            th = yf.Ticker(t).funds_data.top_holdings
            if th is None or th.empty:
                return []
            return [{"symbol": str(s), "name": str(r.get("Name", s)), "pct": round(float(r.get("Holding Percent", 0)) * 100, 2)}
                    for s, r in th.head(10).iterrows()]
        except Exception as e:  # noqa: BLE001
            if "Too Many" in str(e) or "Rate" in str(e):
                time.sleep(20 * (attempt + 1))
                continue
            return []
    return []


def etf_shares_snapshot(t):
    """좌수 추정: sharesOutstanding 이 있으면 그 값, 없으면 순자산 ÷ NAV."""
    import yfinance as yf
    i = None
    for attempt in range(3):
        try:
            i = yf.Ticker(t).info
            break
        except Exception:  # noqa: BLE001
            time.sleep(20 * (attempt + 1))
    if not i:
        return None
    so = i.get("sharesOutstanding")
    if so:
        return int(so)
    ta, nav = i.get("totalAssets"), i.get("navPrice")
    if ta and nav:
        return int(round(ta / nav, -3))
    return None


def sector_strength(items, full):
    """미국 섹터·테마 ETF 흐름: 최근 1주·1달 S&P500(SPY) 대비 초과수익 + RS. 이동평균선은 참고 표시만."""
    spy = full.get("SPY")
    sc = spy["Close"].dropna() if spy is not None else None
    rs = rs_ratings({t: d for t, d in full.items()}, sc.index[-1]) if sc is not None else {}
    out = []
    for e in items:
        df = full.get(e["ticker"])
        if df is None or len(df) < 30:
            continue
        m = momentum(df["Close"].dropna(), sc)
        a, b = m["rel1w"], m["rel1m"]
        if a is None or b is None:
            continue
        if (b >= 1.5 and a >= 0) or (a >= 2 and b > -3):
            lab = "강세"
        elif (b <= -1.5 and a <= 0) or (a <= -2 and b < 3):
            lab = "약세"
        else:
            lab = "횡보"
        out.append({"ticker": e["ticker"], "label": e["label"], "trend": lab, "rs": rs.get(e["ticker"]),
                    "score": round(a + b, 2), **m})
    return sorted(out, key=lambda x: -x["score"])


def run_etf():
    log("===== ETF =====")
    watch = [e for g in ETFS["groups"] for e in g["items"]]
    # 구성종목·좌수는 대량 다운로드 전에 먼저 받는다 (Yahoo 요청 제한 회피). 실패하면 직전 값 사용.
    mpath = CACHE / "etf_meta.json"
    meta = read_json(mpath, {})
    snaps = {}
    for e in watch:
        t = e["ticker"]
        h = etf_holdings(t)
        if h:
            meta[t] = {"holdings": h, "count": len(h), "at": dt.date.today().isoformat()}
        snaps[t] = etf_shares_snapshot(t)
        time.sleep(0.5)
    write_json(mpath, meta)
    log(f"구성종목 {sum(bool(meta.get(e['ticker'], {}).get('holdings')) for e in watch)}/{len(watch)}, 좌수 {sum(bool(v) for v in snaps.values())}/{len(watch)}")
    uni = load_universe("etf", CACHE)
    # 운용자산(순자산)·상장일은 일괄 시세로, 구성종목 수는 개별 조회(30일 캐시)로 — 모두 대량 다운로드 전에
    q = quote_batch([t for t in uni if not LEVERAGED.search(uni[t].get("name", ""))] + ["KRW=X"])
    krw = q.get("KRW=X", {}).get("px") or meta.get("_krw") or 1400
    meta["_krw"] = krw
    min_usd = SETTINGS["etf_min_aum_krw"] / krw
    now_ms = time.time() * 1000
    eligible = {}
    for t, x in q.items():
        na, ft = x.get("aum"), x.get("first")
        if na and na >= min_usd and (not ft or now_ms - ft >= SETTINGS["etf_min_age_days"] * 864e5):
            eligible[t] = na
    month_ago = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    fails = 0
    for t in sorted(eligible):
        m = meta.get(t, {})
        if "count" in m and m.get("at", "") >= month_ago:
            continue
        if fails >= 8:
            break
        h = etf_holdings(t)
        meta[t] = {"holdings": h, "count": len(h), "at": dt.date.today().isoformat()}
        fails = 0 if h else fails + 1
        time.sleep(0.15)
    write_json(mpath, meta)
    min_h = SETTINGS["etf_min_holdings"]
    ok = {t for t in eligible if meta.get(t, {}).get("count", min_h) >= min_h}
    log(f"순자산 {min_usd / 1e8:.1f}억달러(1조원) 이상·상장 6개월 이상 {len(eligible)}개 → 구성종목 {min_h}개 이상 {len(ok)}개 (환율 {krw})")
    for e in watch:
        uni.setdefault(e["ticker"], {"name": e["label"], "sector": "ETF", "industry": "ETF"})
    full = download(list(uni), "13mo")
    trade_date = trade_date_of(full)
    ds = trade_date.strftime("%Y-%m-%d")
    log(f"기준일 {ds} / 시세 {len(full)}개")

    rows, skipped = [], {"lev": 0, "young": 0}
    for t, df in full.items():
        if df.index[-1] != trade_date or df["Volume"].iloc[-1] == 0:
            continue
        name = uni.get(t, {}).get("name", t)
        if LEVERAGED.search(name):
            skipped["lev"] += 1
            continue
        if len(df) < SETTINGS["etf_min_days"]:  # 상장 6개월 미만 제외
            skipped["young"] += 1
            continue
        if t not in ok:  # 순자산 1조원 미만 · 구성종목 10개 미만
            skipped["small"] = skipped.get("small", 0) + 1
            continue
        rows.append({"ticker": t, "name": name, "aum": round(eligible.get(t, 0)), **returns(df)})
    n = SETTINGS["top_n"]
    w1, w1_week = weekly_top("etf", rows, trade_date, n)
    tops = {"top_d1": top_n(rows, "d1", n), "top_w1": w1}
    log(f"집계 {len(rows)}개 (레버리지·인버스 제외 {skipped['lev']}, 상장 1년 미만 제외 {skipped['young']})")

    top_set = {r["ticker"] for v in tops.values() for r in v}
    shown = top_set | {e["ticker"] for e in watch}
    wk = weekly(shown)
    for t in shown:
        if t in full:
            write_chart("etf", t, uni.get(t, {}).get("name", t), full[t], wk.get(t))

    # 상승률 상위 ETF 구성종목은 별도 단계(meta)에서 채움. 여기서는 캐시만 반영.
    for v in tops.values():
        for r in v:
            r["holdings"] = meta.get(r["ticker"], {}).get("holdings", [])

    spath = DATA / "etf_shares.json"
    shares = read_json(spath, {})
    groups = []
    for g in ETFS["groups"]:
        items = []
        for e in g["items"]:
            t = e["ticker"]
            df = full.get(t)
            snap = snaps.get(t)
            if snap:
                shares.setdefault(t, {})[ds] = snap
            hs = sorted(shares.get(t, {}).items())[-15:]
            items.append({**e, **(returns(df) if df is not None else {"close": None, "d1": None, "w1": None}),
                          "name": e["label"], "holdings": meta.get(t, {}).get("holdings", []),
                          "shares": [[d, v] for d, v in hs]})
        groups.append({"name": g["name"], "region": g.get("region", "us"), "items": items})
    write_json(spath, shares)
    strength = sector_strength([e for g in ETFS["groups"] if g.get("region", "us") == "us" and g["name"] != "지수" for e in g["items"]], full)

    write_json(DATA / "etf" / f"{ds}.json", {"market": "etf", "date": ds, "generated_at": now_iso(),
                                             "universe": len(uni), "priced": len(rows), "skipped": skipped, "w1_week": w1_week,
                                             "min_aum_usd": round(min_usd), "krw": krw, "strength": strength, "w1_crit": ETF_CRIT,
                                             **tops, "groups": groups})
    add_index("etf", ds)
    log(f"저장 완료: docs/data/etf/{ds}.json")


# ---------------------------------------------------------------- 거시 지표
def series_close(df, since=None):
    d = df if since is None else df[df.index >= since]
    return [[i.strftime("%Y-%m-%d"), num(v)] for i, v in d["Close"].items() if not pd.isna(v)]


def run_macro_us():
    import requests
    log("===== 미국 거시 지표 =====")
    out = read_json(DATA / "macro" / "us.json", {"series": {}})
    S = out.setdefault("series", {})
    idx = download(["^DJI", "^IXIC", "^GSPC"], "6y")
    for key, t, label in (("dji", "^DJI", "다우"), ("ixic", "^IXIC", "나스닥"), ("spx", "^GSPC", "S&P 500")):
        if t in idx:
            S[key] = {"label": label, "type": "ohlc", "data": bars_of(idx[t])}
    # 원자재·비트코인 (금·구리·WTI는 뉴욕 선물 근월물)
    cm = download(["GC=F", "HG=F", "CL=F", "BTC-USD"], "6y")
    for key, t, label, unit in (("gold", "GC=F", "금", "$/oz"), ("copper", "HG=F", "구리", "$/lb"),
                                ("wti", "CL=F", "WTI 원유", "$/배럴"), ("btc", "BTC-USD", "비트코인", "$")):
        if cm.get(t) is not None:
            S[key] = {"label": label, "type": "ohlc", "unit": unit, "data": bars_of(cm[t])}
    vix = download(["^VIX"], "10y").get("^VIX")
    if vix is not None:
        S["vix"] = {"label": "VIX (변동성지수)", "type": "ohlc", "data": bars_of(vix)}
    # 국채 금리 일봉 (Yahoo: 5년 ^FVX · 10년 ^TNX · 30년 ^TYX, 2년은 국채 2년 선물 수익률 2YY=F)
    ylds = download(["^FVX", "^TNX", "^TYX"], "10y")
    yahoo_yields = {}
    for key, t in (("ust5", "^FVX"), ("ust10", "^TNX"), ("ust30", "^TYX")):
        df = ylds.get(t)
        if df is None or len(df) < 100:
            continue
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if (df["High"] > df["Low"]).mean() > 0.5:  # 고가·저가가 실제로 있는 경우만 일봉
            yahoo_yields[key] = bars_of(df)

    # CNN 공포탐욕지수 · Put/Call (기존 기록과 합쳐서 계속 쌓음)
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Referer": "https://edition.cnn.com/", "Origin": "https://edition.cnn.com"}
    try:
        j = None
        for start in ("2020-07-01", "2023-01-01"):
            r = requests.get(f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}", headers=hdr, timeout=60)
            if r.ok:
                j = r.json()
                break
        if j:
            for key, src, label in (("fg", "fear_and_greed_historical", "공포탐욕지수 (CNN)"),
                                    ("pc", "put_call_options", "Put/Call 비율 (5일 평균, CNN)")):
                old = {d: v for d, v in S.get(key, {}).get("data", [])}
                for p in j[src]["data"]:
                    d = dt.datetime.fromtimestamp(p["x"] / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
                    old[d] = round(float(p["y"]), 3 if key == "pc" else 1)
                S[key] = {"label": label, "type": "line", "data": sorted([[d, v] for d, v in old.items()])}
            try:  # 2011년부터의 과거 기록 (whit3rabbit/fear-greed-data, MIT)
                import io
                hcsv = requests.get("https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv", timeout=60).text
                hdf = pd.read_csv(io.StringIO(hcsv))
                old = {d: v for d, v in S["fg"]["data"]}
                for _, r in hdf.iterrows():
                    old.setdefault(str(r["Date"])[:10], round(float(r["Fear Greed"]), 1))
                S["fg"]["data"] = sorted([[d, v] for d, v in old.items()])
            except Exception as e:  # noqa: BLE001
                log("공포탐욕 과거 기록 실패:", e)
            fg = j.get("fear_and_greed", {})
            S["fg"]["now"] = {"score": round(fg.get("score", 0), 1), "rating": fg.get("rating", "")}
    except Exception as e:  # noqa: BLE001
        log("CNN 실패:", e)

    # 미국 재무부 국채 금리 (10년치)
    try:
        frames = []
        y0 = dt.date.today().year
        for y in range(y0 - 9, y0 + 1):
            u = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all"
                 f"?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
            try:
                import io
                frames.append(pd.read_csv(io.StringIO(requests.get(u, headers=hdr, timeout=60).text)))
            except Exception as e:  # noqa: BLE001
                log(f"  국채 {y} 실패:", e)
        tr = pd.concat(frames)
        tr["Date"] = pd.to_datetime(tr["Date"], format="%m/%d/%Y")
        tr = tr.sort_values("Date").drop_duplicates("Date")
        for key, col, label in (("ust2", "2 Yr", "미국 국채 2년"), ("ust5", "5 Yr", "미국 국채 5년"), ("ust10", "10 Yr", "미국 국채 10년"),
                                ("ust20", "20 Yr", "미국 국채 20년"), ("ust30", "30 Yr", "미국 국채 30년")):
            if key in yahoo_yields:
                S[key] = {"label": label, "type": "ohlc", "unit": "%", "data": yahoo_yields[key]}
                continue
            d = tr[["Date", col]].dropna()
            S[key] = {"label": label, "type": "line", "unit": "%",
                      "data": [[r.Date.strftime("%Y-%m-%d"), float(r[col])] for _, r in d.iterrows()]}
    except Exception as e:  # noqa: BLE001
        log("국채 금리 실패:", e)

    out["updated"] = now_iso()
    write_json(DATA / "macro" / "us.json", out, compact=True)
    log("저장 완료: docs/data/macro/us.json")


def kofia(obj, start, end):
    import requests
    body = {"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D", "tmpV45": start, "tmpV46": end, "OBJ_NM": obj}}
    r = requests.post("https://freesis.kofia.or.kr/meta/getMetaDataList.do", json=body,
                      headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}, timeout=90)
    r.raise_for_status()
    return r.json().get("ds1") or []


def run_macro_kr():
    log("===== 한국 거시 지표 =====")
    out = read_json(DATA / "macro" / "kr.json", {"series": {}})
    S = out.setdefault("series", {})
    kk = download(["^KS11", "^KQ11"], "4y")
    if kk.get("^KS11") is not None:
        S["kospi"] = {"label": "코스피", "type": "ohlc", "data": bars_of(kk["^KS11"])}
    if kk.get("^KQ11") is not None:
        S["kosdaq"] = {"label": "코스닥", "type": "ohlc", "data": bars_of(kk["^KQ11"])}
    # 일본 니케이225 · 대만 가권지수 (아시아 장 마감 후 같은 단계에서 갱신)
    asia = download(["^N225", "^TWII"], "4y")
    for t, f, label in (("^N225", "jp", "니케이 225"), ("^TWII", "tw", "대만 가권지수")):
        if asia.get(t) is not None:
            write_json(DATA / "macro" / f"{f}.json", {"updated": now_iso(), "series": {
                "index": {"label": label, "type": "ohlc", "data": bars_of(asia[t])}}}, compact=True)
    end = dt.date.today()
    start = (end - dt.timedelta(days=365 * 3 + 10)).strftime("%Y%m%d")
    end = end.strftime("%Y%m%d")
    fmt = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"  # noqa: E731
    try:  # 증시자금추이: TMPV2 = 투자자예탁금 (백만원)
        rows = kofia("STATSCU0100000060BO", start, end)
        S["deposit"] = {"label": "투자자 예탁금", "type": "line", "unit": "조원",
                        "data": sorted([[fmt(r["TMPV1"]), round(r["TMPV2"] / 1e6, 2)] for r in rows if r.get("TMPV2")])}
    except Exception as e:  # noqa: BLE001
        log("예탁금 실패:", e)
    try:  # 신용공여 잔고: TMPV2 = 신용거래융자 전체, TMPV3 = 유가증권, TMPV4 = 코스닥 (백만원)
        rows = kofia("STATSCU0100000070BO", start, end)
        S["credit"] = {"label": "신용잔고 (신용거래융자)", "type": "line", "unit": "조원",
                       "data": sorted([[fmt(r["TMPV1"]), round(r["TMPV2"] / 1e6, 2)] for r in rows if r.get("TMPV2")])}
    except Exception as e:  # noqa: BLE001
        log("신용잔고 실패:", e)
    out["updated"] = now_iso()
    write_json(DATA / "macro" / "kr.json", out, compact=True)
    log("저장 완료: docs/data/macro/kr.json")
    run_vkospi()


def run_vkospi():
    """코스피 200 변동성지수(VKOSPI) — 한국거래소 Open API (인증키: 환경변수 KRX_API_KEY).
    KRX는 다음 날 공개하므로, 비어 있는 날짜는 다음 실행에서 다시 받는다."""
    import os
    import requests
    key = os.environ.get("KRX_API_KEY")
    if not key:
        log("KRX_API_KEY 없음 — VKOSPI 건너뜀")
        return
    log("===== VKOSPI =====")
    cpath = CACHE / "vkospi.json"
    cache = read_json(cpath, {})
    kr = read_json(DATA / "macro" / "kr.json", {"series": {}})
    days = [b[0] for b in kr.get("series", {}).get("kospi", {}).get("data", [])]
    cut = (dt.date.today() - dt.timedelta(days=365 * 3 + 10)).isoformat()
    days = [d for d in days if d >= cut]
    if not days:  # 코스피 날짜가 없으면 최근 평일로
        days = [str(d.date()) for d in pd.bdate_range(end=dt.date.today(), periods=760)]
    today = dt.date.today()
    todo = [d for d in days if d not in cache] + [today.isoformat(), (today - dt.timedelta(days=1)).isoformat()]
    got = 0
    for d in dict.fromkeys(todo):
        if d in cache:
            continue
        try:
            r = requests.get("https://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd", params={"basDd": d.replace("-", "")},
                             headers={"AUTH_KEY": key}, timeout=30)
            for x in (r.json().get("OutBlock_1") or []):
                if x.get("IDX_NM") == "코스피 200 변동성지수":
                    f = lambda k: float(str(x.get(k, "0")).replace(",", "") or 0)  # noqa: E731
                    if f("CLSPRC_IDX"):
                        cache[d] = [f("OPNPRC_IDX") or f("CLSPRC_IDX"), f("HGPRC_IDX") or f("CLSPRC_IDX"),
                                    f("LWPRC_IDX") or f("CLSPRC_IDX"), f("CLSPRC_IDX")]
                        got += 1
        except Exception as e:  # noqa: BLE001
            log("  VKOSPI 오류", d, repr(e)[:100])
        time.sleep(0.15)
    write_json(cpath, dict(sorted(cache.items())))
    kr.setdefault("series", {})["vkospi"] = {"label": "VKOSPI (코스피200 변동성지수)", "type": "ohlc",
                                             "data": [[d, *v, 0] for d, v in sorted(cache.items()) if d >= cut]}
    kr["updated"] = now_iso()
    write_json(DATA / "macro" / "kr.json", kr, compact=True)
    log(f"VKOSPI 새로 {got}일, 총 {len(cache)}일")


# ---------------------------------------------------------------- 보조 정보 (별도 프로세스에서 실행)
def run_meta():
    """대량 다운로드 후에는 Yahoo가 종목 정보 요청을 막는 경우가 있어, 새 프로세스에서 따로 받는다.
    미국: 시가총액·PER·PSR / ETF: 상승률 상위 ETF 구성종목. 최신 날짜 파일을 보완한다."""
    log("===== 보조 정보 =====")
    idx = read_json(DATA / "index.json", {})
    if idx.get("etf"):
        p = DATA / "etf" / f"{idx['etf'][0]}.json"
        day = read_json(p, None)
        if day:
            mpath = CACHE / "etf_meta.json"
            meta = read_json(mpath, {})
            week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
            tops = [r for k in ("top_d1", "top_w1") for r in day[k]]
            fails = 0
            for t in list(dict.fromkeys(r["ticker"] for r in tops)):
                m = meta.get(t, {})
                if m.get("holdings") and m.get("at", "") >= week_ago:
                    continue
                if fails >= 8:
                    break
                h = etf_holdings(t)
                if h:
                    meta[t] = {"holdings": h, "count": len(h), "at": dt.date.today().isoformat()}
                fails = 0 if h else fails + 1
                time.sleep(0.6)
            write_json(mpath, meta)
            for r in tops:
                r["holdings"] = meta.get(r["ticker"], {}).get("holdings", [])
            write_json(p, day)
            log(f"ETF 구성종목 {sum(1 for r in tops if r['holdings'])}/{len(tops)}")

    for mk in ("us", "jp", "tw"):
        if not idx.get(mk):
            continue
        p = DATA / mk / f"{idx[mk][0]}.json"
        day = read_json(p, None)
        if day:
            every = day["newhigh"] + day.get("rising", []) + day["top_d1"] + day["top_w1"]
            order = list(dict.fromkeys(r["ticker"] for r in every))  # 신고가 → 일간 → 주간 순으로 우선
            fu = fundamentals(order, {r["ticker"]: r["close"] for r in every})
            for r in every:
                f = fu.get(r["ticker"], {})
                if f.get("mcap") and not r.get("mcap"):
                    r["mcap"] = f["mcap"]
                r["per"] = f.get("per") or r.get("per")
                r["psr"] = f.get("psr")
            write_json(p, day)
            log(f"[{mk}] 재무 정보 {sum(1 for t in fu.values() if t.get('per') or t.get('psr'))}/{len({r['ticker'] for r in every})}")

# ---------------------------------------------------------------- 실행
JOBS = {"etf": run_etf, "macro_us": run_macro_us, "macro_kr": run_macro_kr,
        "us": lambda: run_stocks("us"), "kr": lambda: run_stocks("kr"), "jp": lambda: run_stocks("jp"),
        "tw": lambda: run_stocks("tw"), "vkospi": run_vkospi,
        "meta": run_meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="all")
    a = ap.parse_args()
    CACHE.mkdir(exist_ok=True)
    targets = [k for k in JOBS if k != "meta"] if a.market == "all" else [m.strip() for m in a.market.split(",") if m.strip()]
    failed = []
    for m in targets:
        try:
            JOBS[m]()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            log(f"[{m}] 실패: {e}")
            failed.append(m)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
