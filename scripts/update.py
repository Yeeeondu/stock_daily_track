#!/usr/bin/env python3
"""매일 실행: 52주/역대 신고가·신저가 + ETF 등락 집계 → docs/data/ 에 JSON 저장.

사용법:  python scripts/update.py --market jp|us|all
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


# ---------------------------------------------------------------- 시세 받기
def _clean(df):
    df = df[[c for c in COLS if c in df.columns]].copy()
    df = df.dropna(subset=["Close"])
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)  # 현지 날짜 유지
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


def download(tickers, period):
    """yfinance 일괄 다운로드 (묶음 단위, 실패분 1회 재시도). {ticker: DataFrame}"""
    import yfinance as yf

    out, todo = {}, list(dict.fromkeys(tickers))
    size = SETTINGS["chunk_size"]
    for rnd in range(2):
        missing = []
        for i in range(0, len(todo), size):
            part = todo[i:i + size]
            try:
                raw = yf.download(part, period=period, interval="1d", group_by="ticker",
                                  auto_adjust=False, actions=False, threads=True, progress=False)
            except Exception as e:  # noqa: BLE001
                log("  다운로드 오류:", e)
                missing += part
                time.sleep(15)
                continue
            for t in part:
                sub = _pick(raw, t)
                if sub is None or sub.empty:
                    missing.append(t)
                else:
                    out[t] = sub
            log(f"  {period}: {min(i + size, len(todo))}/{len(todo)}")
            time.sleep(SETTINGS["sleep_sec"])
        if not missing or rnd == 1:
            break
        log(f"  재시도 {len(missing)}종목")
        todo = missing
        time.sleep(20)
    return out


# ---------------------------------------------------------------- 계산
def returns(df):
    c = df["Close"].dropna()
    last, d = c.iloc[-1], c.index[-1]
    base_m = c[c.index <= d - pd.DateOffset(months=1)]
    return {
        "close": num(last),
        "d1": pct(last, c.iloc[-2]) if len(c) > 1 else None,
        "d5": pct(last, c.iloc[-6]) if len(c) > 5 else None,
        "m1": pct(last, base_m.iloc[-1]) if len(base_m) else None,
    }


def analyze(df, trade_date):
    """당일 신고가/신저가 여부 판정. 반환: (kind, ref) 또는 None"""
    if df.index[-1] != trade_date:
        return None
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < SETTINGS["min_history_days"] + 1:
        return None  # 상장 1년 미만 등 이력 부족
    lb, r = SETTINGS["lookback_days"], SETTINGS["rules"]
    t, p = df.iloc[-1], df.iloc[-2]
    win = df.iloc[-(lb + 1):-1]
    hi, lo = win["High"].max(), win["Low"].min()
    if (t.High > hi and (not r["high_require_up"] or t.Close > p.Close)
            and (not r["high_require_bullish"] or t.Close > t.Open)):
        return "high", hi
    if (t.Low < lo and (not r["low_require_down"] or t.Close < p.Close)
            and (not r["low_require_bearish"] or t.Close < t.Open)):
        return "low", lo
    return None


def all_time_flags(hits, hist, trade_date):
    """신고가/신저가 종목만 전체 기간 시세를 받아 역대 기록 여부 판정."""
    if not hits:
        return {}
    full = download([h["ticker"] for h in hits], "max")
    flags = {}
    for h in hits:
        t = h["ticker"]
        f = full.get(t)
        today = hist[t].iloc[-1]
        if f is None or f.empty:
            continue
        prior = f[f.index < trade_date]
        if prior.empty:
            continue
        since = prior.index[0].strftime("%Y-%m-%d")
        if h["kind"] == "high":
            flags[t] = (bool(today.High > prior["High"].max()), since)
        else:
            flags[t] = (bool(today.Low < prior["Low"].min()), since)
    return flags


def english_names(tickers):
    cpath = CACHE / "names.json"
    cache = json.loads(cpath.read_text("utf-8")) if cpath.exists() else {}
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
        cpath.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True), "utf-8")
    return cache


def write_chart(market, t, name, df, trade_date):
    cut = trade_date - pd.DateOffset(days=SETTINGS["chart_days"])
    d = df[df.index >= cut]
    bars = [[i.strftime("%Y-%m-%d"), num(r.Open), num(r.High), num(r.Low), num(r.Close),
             0 if pd.isna(r.Volume) else int(r.Volume)] for i, r in d.iterrows()]
    out = DATA / "charts" / market
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{safe(t)}.json").write_text(json.dumps(
        {"ticker": t, "name": name, "updated": trade_date.strftime("%Y-%m-%d"), "bars": bars},
        ensure_ascii=False, separators=(",", ":")), "utf-8")


def criteria_text():
    r = SETTINGS["rules"]
    hi = "·".join([x for x, on in (("상승", r["high_require_up"]), ("양봉", r["high_require_bullish"])) if on])
    lo = "·".join([x for x, on in (("하락", r["low_require_down"]), ("음봉", r["low_require_bearish"])) if on])
    return {
        "high": f"{hi + ' 마감 · ' if hi else ''}장중 52주({SETTINGS['lookback_days']}거래일) 고가 돌파",
        "low": f"{lo + ' 마감 · ' if lo else ''}장중 52주({SETTINGS['lookback_days']}거래일) 저가 이탈",
    }


# ---------------------------------------------------------------- 실행
def run(market):
    log(f"===== {market.upper()} =====")
    uni = load_universe(market, CACHE)
    hist = download(list(uni), "13mo")
    if not hist:
        raise RuntimeError("시세를 하나도 받지 못했습니다")
    trade_date = pd.Series([df.index[-1] for df in hist.values()]).mode().max()
    ds = trade_date.strftime("%Y-%m-%d")
    log(f"기준일 {ds} / 시세 {len(hist)}종목")

    hits = []
    for t, df in hist.items():
        res = analyze(df, trade_date)
        if not res:
            continue
        kind, ref = res
        m = uni[t]
        hits.append({"ticker": t, "kind": kind, "ref": num(ref), "name": m["name"],
                     "name_local": m.get("name_local", ""), "sector": m["sector"],
                     "industry": m["industry"], "small": bool(m.get("small")), **returns(df)})
    log(f"신고가 {sum(h['kind'] == 'high' for h in hits)} / 신저가 {sum(h['kind'] == 'low' for h in hits)}")

    flags = all_time_flags(hits, hist, trade_date)
    if market == "jp" and SETTINGS.get("jp_english_names"):
        names = english_names([h["ticker"] for h in hits])
        for h in hits:
            h["name"] = names.get(h["ticker"], h["name"])
    for h in hits:
        h["ath"], h["since"] = flags.get(h["ticker"], (False, None))
        write_chart(market, h["ticker"], h["name"], hist[h["ticker"]], trade_date)

    # ETF
    etf_list = ETFS.get(market, [])
    etf_hist = download([e["ticker"] for e in etf_list], "13mo") if etf_list else {}
    etfs = []
    for e in etf_list:
        df = etf_hist.get(e["ticker"])
        if df is None or df.empty:
            etfs.append({**e, "close": None, "d1": None, "d5": None, "m1": None})
            continue
        hi52 = df[df.index > df.index[-1] - pd.DateOffset(weeks=52)]["High"].max()
        etfs.append({**e, **returns(df), "asof": df.index[-1].strftime("%Y-%m-%d"),
                     "from_high": pct(df["Close"].iloc[-1], hi52)})
        write_chart(market, e["ticker"], e["label"], df, df.index[-1])

    def pick(kind, ath):
        rows = [{k: v for k, v in h.items() if k != "kind"} for h in hits if h["kind"] == kind and h["ath"] == ath]
        return sorted(rows, key=lambda x: (x["d1"] is None, -(x["d1"] or 0) if kind == "high" else (x["d1"] or 0)))

    day = {
        "market": market, "date": ds,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "universe": len(uni), "priced": len(hist), "criteria": criteria_text(),
        "newhigh": {"ath": pick("high", True), "w52": pick("high", False)},
        "newlow": {"atl": pick("low", True), "w52": pick("low", False)},
        "etfs": etfs,
    }
    (DATA / market).mkdir(parents=True, exist_ok=True)
    (DATA / market / f"{ds}.json").write_text(json.dumps(day, ensure_ascii=False, indent=1), "utf-8")

    ipath = DATA / "index.json"
    idx = json.loads(ipath.read_text("utf-8")) if ipath.exists() else {}
    idx[market] = sorted(set(idx.get(market, [])) | {ds}, reverse=True)
    idx["updated"] = day["generated_at"]
    ipath.write_text(json.dumps(idx, ensure_ascii=False, indent=1), "utf-8")
    log(f"저장 완료: docs/data/{market}/{ds}.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="all", choices=["jp", "us", "all"])
    a = ap.parse_args()
    CACHE.mkdir(exist_ok=True)
    failed = []
    for m in (["jp", "us"] if a.market == "all" else [a.market]):
        try:
            run(m)
        except Exception as e:  # noqa: BLE001
            log(f"[{m}] 실패: {e}")
            failed.append(m)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
