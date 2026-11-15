import io, json, re, requests, pandas as pd
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
def t(name,f):
    try: print("OK  ",name,"→",str(f())[:900])
    except Exception as e: print("FAIL",name,"→",repr(e)[:300])
def treas(y):
    u=f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv"
    df=pd.read_csv(io.StringIO(requests.get(u,headers=UA,timeout=60).text)); return len(df), list(df.columns), df.head(1).values.tolist()
t("Treasury 2026",lambda: treas(2026)); t("Treasury 2023",lambda: treas(2023))
t("FRED 120s",lambda: requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2",headers=UA,timeout=120).text[-80:])
def naver():
    r=requests.get("https://finance.naver.com/sise/sise_deposit.naver",headers=UA,timeout=30)
    txt=r.content.decode("euc-kr","replace"); i=txt.find("고객예탁금")
    return r.status_code, len(txt), re.sub(r"\s+"," ",txt[i:i+1500])
t("Naver raw",naver)
def kofia():
    body={"dmSearch":{"tmpV40":"1000000","tmpV41":"1","tmpV1":"D","tmpV45":"20231101","tmpV46":"20261113","OBJ_NM":"STATSCU0100000060BO"}}
    r=requests.post("https://freesis.kofia.or.kr/meta/getMetaDataList.do",json=body,headers={**UA,"Content-Type":"application/json"},timeout=60)
    j=r.json(); ds=j.get("ds1") or j; return r.status_code, (len(ds), ds[:2]) if isinstance(ds,list) else str(j)[:600]
t("KOFIA freesis",kofia)
import yfinance as yf
def etfsh():
    out={}
    for s in ("SOXX","JETS","IGV","ITA"):
        tk=yf.Ticker(s)
        try: g=tk.get_shares_full(start="2026-09-01"); out[s]=None if g is None else (len(g), g.tail(2).to_dict())
        except Exception as e: out[s]=repr(e)[:80]
    return out
t("yf get_shares_full ETF",etfsh)
