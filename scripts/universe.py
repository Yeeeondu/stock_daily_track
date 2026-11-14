"""종목 유니버스(전체 종목 목록 + 업종) 불러오기.
- 일본: JPX(일본거래소) 상장종목 일람 엑셀 (프라임/스탠다드/그로스 내국주식 전체)
- 미국: 위키백과 S&P 500 / 400 / 600 구성종목 (= S&P 1500, GICS 업종 포함)
가져오기에 실패하면 cache/ 에 저장된 직전 목록을 사용한다."""
import io
import json
from pathlib import Path

import pandas as pd
import requests

from industry_map import jp_category, us_category

UA = {"User-Agent": "Mozilla/5.0 (sector-board; GitHub Actions)"}
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


def _us():
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


def load_universe(market: str, cache_dir: Path):
    path = cache_dir / f"universe_{market}.json"
    try:
        uni = _jp() if market == "jp" else _us()
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
