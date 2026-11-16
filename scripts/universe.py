"""종목 유니버스(전체 종목 목록 + 업종) 불러오기.
- 일본: JPX(일본거래소) 상장종목 일람 엑셀 (프라임/스탠다드/그로스 내국주식 전체)
- 미국: 나스닥 스크리너(미국 상장 전 종목, 시가총액 하한 적용) + 위키백과 S&P 1500의 GICS 업종
- 한국: 한국거래소 KIND 상장법인 목록 (코스피·코스닥)
- ETF: 나스닥트레이더 상장 종목 목록에서 ETF 표시된 것 전부
가져오기에 실패하면 cache/ 에 저장된 직전 목록을 사용한다."""
import io
import json
from pathlib import Path

import pandas as pd
import requests

from industry_map import NASDAQ_SECTOR, jp_category, tw_category, us_category

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
NASDAQ_SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25000&download=true"
KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
NASDAQ_SYMDIR = "https://www.nasdaqtrader.com/dynamic/SymDir/{}.txt"
JPX_PAGE = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
JPX_FALLBACK = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
SP_PAGES = [
    ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "S&P500"),
    ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "S&P400"),
    ("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", "S&P600"),
]


def _jpx_excel_url():
    """안내 페이지에서 최신 엑셀 링크를 찾는다 (파일 주소가 자주 바뀜)."""
    import re
    from urllib.parse import urljoin
    try:
        html = requests.get(JPX_PAGE, headers=UA, timeout=60).text
        links = re.findall(r'href="([^"]+\.xlsx?)"', html)
        if links:
            pref = [l for l in links if "data_j" in l] or links
            return urljoin(JPX_PAGE, pref[0])
    except Exception as e:  # noqa: BLE001
        print("JPX 페이지 확인 실패:", e, flush=True)
    return JPX_FALLBACK


def _jp():
    url = _jpx_excel_url()
    print("JPX 종목목록:", url, flush=True)
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content), dtype=str)
    df = df[df["市場・商品区分"].fillna("").str.contains("内国株式")]
    out = {}
    for _, x in df.iterrows():
        code = str(x["コード"]).strip()
        sector, ind = jp_category(x.get("33業種区分", ""))
        size = str(x.get("規模区分", "") or "").strip()
        out[f"{code}.T"] = {
            "name": str(x["銘柄名"]).strip(),
            "name_local": str(x["銘柄名"]).strip(),
            "sector": sector,
            "industry": ind,
            "small": ("Small" in size) or size in ("", "-", "nan"),
            "market": str(x["市場・商品区分"]).split("（")[0],
        }
    return out


def _find_col(cols, *keys):
    for c in cols:
        lc = str(c).lower()
        if any(k in lc for k in keys):
            return c
    return None


def _sp1500():
    out = {}
    for url, idx in SP_PAGES:
        html = requests.get(url, headers=UA, timeout=60).text
        table = None
        for t in pd.read_html(io.StringIO(html)):
            sym = _find_col(t.columns, "symbol", "ticker")
            sec = _find_col(t.columns, "gics sector")
            if sym is not None and sec is not None:
                table = t
                break
        if table is None:
            raise RuntimeError(f"표를 찾지 못함: {url}")
        sym = _find_col(table.columns, "symbol", "ticker")
        sec = _find_col(table.columns, "gics sector")
        sub = _find_col(table.columns, "sub-industry")
        nm = _find_col(table.columns, "security", "company")
        for _, x in table.iterrows():
            t = str(x[sym]).strip().replace(".", "-")
            if not t or t == "nan" or t in out:
                continue
            sector, ind = us_category(x[sec], x[sub] if sub is not None else "")
            out[t] = {
                "name": str(x[nm]).strip() if nm is not None else t,
                "name_local": "",
                "sector": sector,
                "industry": ind,
                "small": idx == "S&P600",
                "market": idx,
            }
    return out


def _us(min_mcap=3e8):
    """미국 상장 전 종목 중 시가총액 min_mcap 이상. S&P 1500 종목은 GICS 업종으로 덮어씀."""
    try:
        sp = _sp1500()
    except Exception as e:  # noqa: BLE001
        print("S&P1500 목록 실패:", e, flush=True)
        sp = {}
    out = {}
    try:
        j = requests.get(NASDAQ_SCREENER, headers=UA, timeout=90).json()
        for r in j["data"]["rows"]:
            sym = str(r.get("symbol", "")).strip().replace("/", "-")
            if not sym or "^" in sym or " " in sym:
                continue
            try:
                mcap = float(r.get("marketCap") or 0)
            except ValueError:
                mcap = 0
            if mcap < min_mcap:
                continue
            name = str(r.get("name", sym))
            for suf in (" Common Stock", " Class A Common Stock", " Ordinary Shares", " American Depositary Shares"):
                name = name.split(suf)[0]
            sec = NASDAQ_SECTOR.get(r.get("sector") or "", "기타")
            ind = (r.get("industry") or "").strip() or sec
            out[sym] = {"name": name.strip(), "name_local": "", "sector": sec, "industry": ind,
                        "small": mcap < 2e9, "market": "US", "mcap": mcap}
    except Exception as e:  # noqa: BLE001
        print("나스닥 스크리너 실패:", e, flush=True)
    for t, m in sp.items():
        base = out.get(t, {})
        out[t] = {**base, **m, "small": base.get("small", m["small"]), "mcap": base.get("mcap")}
    return out


def _kr():
    r = requests.get(KIND_URL, headers=UA, timeout=90)
    r.encoding = "euc-kr"
    df = pd.read_html(io.StringIO(r.text), converters={"종목코드": str})[0]
    out = {}
    for _, x in df.iterrows():
        mk = str(x["시장구분"])
        suf = ".KQ" if "코스닥" in mk else ".KS" if ("유가" in mk or "코스피" in mk) else None
        if not suf:
            continue
        code = str(x["종목코드"]).strip().zfill(6)
        ind = str(x.get("업종", "") or "").strip()
        out[code + suf] = {"name": str(x["회사명"]).strip(), "name_local": "", "sector": ind,
                           "industry": ind, "small": False, "market": "코스닥" if suf == ".KQ" else "코스피"}
    return out


def _tw():
    """대만: TWSE 상장(.TW) + TPEx 상장(.TWO) 보통주 (CFI 코드 ES로 시작)."""
    out = {}
    for mode, suf in ((2, ".TW"), (4, ".TWO")):
        r = requests.get(f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}", headers=UA, timeout=120)
        r.encoding = "cp950"
        df = pd.read_html(io.StringIO(r.text), header=0)[0]
        cols = list(df.columns)
        cname = next(c for c in cols if "代號" in str(c))
        cind = next((c for c in cols if "產業" in str(c)), None)
        ccfi = next((c for c in cols if "CFI" in str(c)), None)
        for _, x in df.iterrows():
            cfi = str(x[ccfi]) if ccfi is not None else ""
            if not cfi.startswith("ES"):
                continue
            parts = str(x[cname]).replace("\u3000", " ").split()
            if len(parts) < 2 or not parts[0].isdigit():
                continue
            sector, ind = tw_category(str(x[cind]) if cind is not None else "")
            out[parts[0] + suf] = {"name": " ".join(parts[1:]), "name_local": " ".join(parts[1:]),
                                   "sector": sector, "industry": ind, "small": False,
                                   "market": "TWSE" if suf == ".TW" else "TPEx"}
    return out


def _etf():
    out = {}
    for f in ("nasdaqlisted", "otherlisted"):
        df = pd.read_csv(io.StringIO(requests.get(NASDAQ_SYMDIR.format(f), headers=UA, timeout=60).text), sep="|")
        df = df[df["ETF"] == "Y"]
        sym_col = "Symbol" if "Symbol" in df.columns else "ACT Symbol"
        if "Test Issue" in df.columns:
            df = df[df["Test Issue"] != "Y"]
        for _, x in df.iterrows():
            sym = str(x[sym_col]).strip().replace(".", "-")
            if not sym or sym == "nan" or "$" in sym:
                continue
            out[sym] = {"name": str(x["Security Name"]).strip(), "name_local": "", "sector": "ETF",
                        "industry": "ETF", "small": False, "market": "ETF"}
    return out


def load_universe(market: str, cache_dir: Path, us_min_mcap=3e8):
    path = cache_dir / f"universe_{market}.json"
    try:
        uni = _us(us_min_mcap) if market == "us" else {"jp": _jp, "kr": _kr, "tw": _tw, "etf": _etf}[market]()
        if len(uni) < 300:
            raise RuntimeError(f"종목 수가 너무 적음: {len(uni)}")
        path.write_text(json.dumps(uni, ensure_ascii=False, indent=0), "utf-8")
        print(f"[{market}] 유니버스 {len(uni)}종목 (새로 받음)", flush=True)
        return uni
    except Exception as e:  # noqa: BLE001
        if path.exists():
            uni = json.loads(path.read_text("utf-8"))
            print(f"[{market}] 유니버스 받기 실패({e}) → 캐시 {len(uni)}종목 사용", flush=True)
            return uni
        raise
