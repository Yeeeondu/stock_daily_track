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
    c = df["Close"].dropna()
    last = c.iloc[-1]
    return {
        "close": num(last),
        "d1": pct(last, c.iloc[-2]) if len(c) > 1 else None,
        "w1": pct(last, c.iloc[-6]) if len(c) > 5 else None,
    }


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


def write_chart(market, t, name, df, wk=None):
    cut = df.index[-1] - pd.DateOffset(days=SETTINGS["chart_days"])
    obj = {"ticker": t, "name": name, "updated": df.index[-1].strftime("%Y-%m-%d"), "bars": bars_of(df, cut)}
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
    fresh = lambda t: t in cache and (today - dt.date.fromisoformat(cache[t]["at"])).days < 7  # noqa: E731
    for t in [t for t in tickers if not fresh(t)]:
        for attempt in range(2):
            try:
                i = yf.Ticker(t).info
                cache[t] = {"at": today.isoformat(), "shares": i.get("sharesOutstanding") or i.get("impliedSharesOutstanding"),
                            "eps": i.get("trailingEps"), "rev": i.get("totalRevenue"), "mcap": i.get("marketCap")}
                break
            except Exception:  # noqa: BLE001
                time.sleep(15 * (attempt + 1))
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
    hist = download(list(uni), "13mo")
    if not hist:
        raise RuntimeError("시세를 하나도 받지 못했습니다")
    trade_date = trade_date_of(hist)
    ds = trade_date.strftime("%Y-%m-%d")
    log(f"기준일 {ds} / 시세 {len(hist)}종목")

    rows, highs = [], []
    for t, df in hist.items():
        if df.index[-1] != trade_date or len(df) < 7:
            continue
        if df["Volume"].iloc[-1] == 0:
            continue
        m = uni[t]
        row = {"ticker": t, "name": m["name"], "name_local": m.get("name_local", ""),
               "sector": m["sector"], "industry": m["industry"], "small": bool(m.get("small")), **returns(df)}
        rows.append(row)
        ref = is_new_high(df)
        if ref is not None:
            highs.append({**row, "ref": num(ref)})

    n = SETTINGS["top_n"]
    top_d1, top_w1 = top_n(rows, "d1", n), top_n(rows, "w1", n)
    flags = ath_flags([h["ticker"] for h in highs], hist, trade_date)
    for h in highs:
        h["ath"], h["since"] = flags.get(h["ticker"], (False, None))
    highs.sort(key=lambda r: -(r["d1"] or 0))
    log(f"신고가 {len(highs)} (역대 {sum(h['ath'] for h in highs)})")

    shown = {r["ticker"] for r in highs + top_d1 + top_w1}
    every = highs + top_d1 + top_w1
    if market == "jp" and SETTINGS.get("jp_english_names"):
        names = english_names(sorted(shown))
        for r in every:
            r["name"] = names.get(r["ticker"], r["name"])
    if market == "us":
        rs = rs_ratings(hist, trade_date)
        fu = fundamentals(sorted(shown), {r["ticker"]: r["close"] for r in every})
        for r in every:
            r["rs"] = rs.get(r["ticker"])
            f = fu.get(r["ticker"], {})
            r["mcap"] = f.get("mcap") or uni[r["ticker"]].get("mcap")
            r["per"], r["psr"] = f.get("per"), f.get("psr")
    wk = weekly(shown)
    for t in shown:
        write_chart(market, t, uni[t]["name"], hist[t], wk.get(t))

    write_json(DATA / market / f"{ds}.json", {
        "market": market, "date": ds, "generated_at": now_iso(),
        "universe": len(uni), "priced": len(rows), "criteria": criteria_text(),
        "newhigh": highs, "top_d1": top_d1, "top_w1": top_w1,
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
            meta[t] = {"holdings": h, "at": dt.date.today().isoformat()}
        snaps[t] = etf_shares_snapshot(t)
        time.sleep(0.5)
    write_json(mpath, meta)
    log(f"구성종목 {sum(bool(meta.get(e['ticker'], {}).get('holdings')) for e in watch)}/{len(watch)}, 좌수 {sum(bool(v) for v in snaps.values())}/{len(watch)}")
    uni = load_universe("etf", CACHE)
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
        if len(df) < SETTINGS["etf_min_days"]:  # 상장 1년 미만 제외
            skipped["young"] += 1
            continue
        rows.append({"ticker": t, "name": name, **returns(df)})
    n = SETTINGS["top_n"]
    tops = {"top_d1": top_n(rows, "d1", n), "top_w1": top_n(rows, "w1", n)}
    log(f"집계 {len(rows)}개 (레버리지·인버스 제외 {skipped['lev']}, 상장 1년 미만 제외 {skipped['young']})")

    top_set = {r["ticker"] for v in tops.values() for r in v}
    shown = top_set | {e["ticker"] for e in watch}
    wk = weekly(shown)
    for t in shown:
        if t in full:
            write_chart("etf", t, uni.get(t, {}).get("name", t), full[t], wk.get(t))

    # 상승률 상위 ETF 구성종목 (7일 캐시, 요청 제한 대비 잠깐 쉬고 시작)
    time.sleep(60)
    today = dt.date.today().isoformat()
    for t in sorted(top_set):
        m = meta.get(t, {})
        if m.get("holdings") and m.get("at", "") >= (dt.date.today() - dt.timedelta(days=7)).isoformat():
            continue
        h = etf_holdings(t)
        if h:
            meta[t] = {"holdings": h, "at": today}
        time.sleep(0.6)
    write_json(mpath, meta)
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
        groups.append({"name": g["name"], "items": items})
    write_json(spath, shares)

    write_json(DATA / "etf" / f"{ds}.json", {"market": "etf", "date": ds, "generated_at": now_iso(),
                                             "universe": len(uni), "priced": len(rows), "skipped": skipped,
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
    vix = download(["^VIX"], "10y").get("^VIX")
    if vix is not None:
        S["vix"] = {"label": "VIX (변동성지수)", "type": "line", "data": series_close(vix)}

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
    k = download(["^KS11"], "4y").get("^KS11")
    if k is not None:
        S["kospi"] = {"label": "코스피", "type": "ohlc", "data": bars_of(k)}
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


# ---------------------------------------------------------------- 실행
JOBS = {"etf": run_etf, "macro_us": run_macro_us, "macro_kr": run_macro_kr,
        "us": lambda: run_stocks("us"), "kr": lambda: run_stocks("kr"), "jp": lambda: run_stocks("jp")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="all")
    a = ap.parse_args()
    CACHE.mkdir(exist_ok=True)
    targets = list(JOBS) if a.market == "all" else [m.strip() for m in a.market.split(",") if m.strip()]
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
