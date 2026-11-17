import json, time, yfinance as yf
from yfinance.data import YfData
print("yfinance", yf.__version__)
d = YfData()
syms = ["7203.T","6758.T","9984.T","2330.TW","2317.TW","6488.TWO","AAPL","JPY=X","TWD=X"] + [f"{1300+i}.T" for i in range(190)]
for host in ("query1","query2"):
    try:
        t=time.time()
        r = d.get_raw_json(f"https://{host}.finance.yahoo.com/v7/finance/quote", params={"symbols": ",".join(syms), "fields": "marketCap,sharesOutstanding,currency,regularMarketPrice,trailingPE,priceToSales"})
        res = r["quoteResponse"]["result"]
        print("OK", host, len(res), round(time.time()-t,1), "s")
        for x in res[:9]: print("  ", x.get("symbol"), x.get("currency"), x.get("marketCap"), x.get("trailingPE"), x.get("regularMarketPrice"))
        print("  with mcap:", sum(1 for x in res if x.get("marketCap")))
        break
    except Exception as e: print("FAIL", host, repr(e)[:300])
