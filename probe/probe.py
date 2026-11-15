import io, json, traceback, requests, pandas as pd
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36","Accept":"application/json, text/plain, */*","Referer":"https://edition.cnn.com/","Origin":"https://edition.cnn.com"}
def t(name,f):
    try: print("OK  ",name,"→",f())
    except Exception as e: print("FAIL",name,"→",repr(e)[:300])
def cnn():
    r=requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata/2023-01-01",headers=UA,timeout=30); r.raise_for_status(); j=r.json()
    return {k:(len(v["data"]) if isinstance(v,dict) and "data" in v else str(v)[:60]) for k,v in j.items()}, j["fear_and_greed_historical"]["data"][0], j.get("put_call_options",{}).get("data",[{}])[-1]
t("CNN F&G",cnn)
def fred(s):
    df=pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}",storage_options=None) if False else pd.read_csv(io.StringIO(requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}",headers=UA,timeout=30).text))
    return len(df), df.tail(1).values.tolist()
for s in ("DGS2","DGS10","DGS30","BAMLC0A0CM"): t("FRED "+s,lambda s=s: fred(s))
def naver(p):
    r=requests.get(f"https://finance.naver.com/sise/sise_deposit.naver?page={p}",headers=UA,timeout=30); r.encoding="euc-kr"
    ts=pd.read_html(io.StringIO(r.text)); big=max(ts,key=len); return len(ts), big.dropna(how="all").head(3).to_string()[:400]
t("Naver deposit p1",lambda: naver(1)); t("Naver deposit p80",lambda: naver(80))
def kind():
    r=requests.get("https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",headers=UA,timeout=60); r.encoding="euc-kr"
    df=pd.read_html(io.StringIO(r.text))[0]; return len(df), list(df.columns), df.head(2).values.tolist()
t("KIND corplist",kind)
def nasdaq():
    out={}
    for f in ("nasdaqlisted","otherlisted"):
        df=pd.read_csv(io.StringIO(requests.get(f"https://www.nasdaqtrader.com/dynamic/SymDir/{f}.txt",headers=UA,timeout=30).text),sep="|")
        out[f]=(len(df), int((df["ETF"]=="Y").sum()))
    return out
t("nasdaqtrader",nasdaq)
def nscreener():
    r=requests.get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5&download=true",headers=UA,timeout=30); j=r.json(); rows=j["data"]["rows"]; return len(rows), rows[0]
t("nasdaq screener",nscreener)
import yfinance as yf
def yfx():
    out={}
    for s in ("^GSPC","^DJI","^IXIC","^VIX","^KS11","^KQ11"):
        h=yf.Ticker(s).history(period="3y"); out[s]=(len(h), str(h.index[-1].date()))
    return out
t("yf indices",yfx)
def hold():
    tk=yf.Ticker("SOXX"); th=tk.funds_data.top_holdings; return th.head(3).to_dict()
t("yf top_holdings SOXX",hold)
def shares():
    out={}
    for s in ("SOXX","JETS","LNGX","ARKG"):
        i=yf.Ticker(s).info; out[s]={k:i.get(k) for k in ("sharesOutstanding","totalAssets","impliedSharesOutstanding","navPrice")}
    return out
t("yf etf shares",shares)
def krx_hist():
    h=yf.download(["005930.KS","035720.KQ"],period="1mo",progress=False,group_by="ticker"); return h.shape
t("yf KR stocks",krx_hist)
def cds():
    r=requests.get("https://www.investing.com/rates-bonds/nvidia-corp-5-years-cds",headers=UA,timeout=30); return r.status_code, len(r.text)
t("investing CDS",cds)
