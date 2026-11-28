import yfinance as yf, collections
ts=["AAPL","MSFT","NVDA","JPM","XOM","KO","CROX","ACM","APP","PLTR","SBC","AMZN"]
for per in ("13mo","18mo","2y"):
    raw=yf.download(ts, period=per, interval="1d", group_by="ticker", auto_adjust=False, progress=False, threads=False)
    last=collections.Counter()
    for t in ts:
        d=raw[t].dropna(how="all")
        last[str(d.index[-1].date()) if len(d) else "none"]+=1
    print("RES", per, dict(last))
h=yf.Ticker("AAPL").history(period="18mo"); print("RES AAPL 18mo tail", [str(x.date()) for x in h.index[-4:]])
