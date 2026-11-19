import time, yfinance as yf
from yfinance.data import YfData
d = YfData()
syms = ["SPY","SOXX","LNGX","GLD","IBIT","TSLY","JETS","KRW=X","XYZETF"]
r = d.get_raw_json("https://query1.finance.yahoo.com/v7/finance/quote", params={"symbols": ",".join(syms)})
for x in r["quoteResponse"]["result"]:
    print(x.get("symbol"), {k: x.get(k) for k in ("netAssets","totalAssets","marketCap","regularMarketPrice","firstTradeDateMilliseconds","quoteType")})
for s in ("GLD","IBIT","TSLY","LNGX"):
    t=time.time()
    try:
        th = yf.Ticker(s).funds_data.top_holdings; print(s, "holdings rows", len(th), round(time.time()-t,2),"s")
    except Exception as e: print(s, "ERR", repr(e)[:100])
