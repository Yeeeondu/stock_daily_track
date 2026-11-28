import yfinance as yf, collections
ts=["AAPL","MSFT","NVDA","AMZN","JPM","XOM","KO","CROX","ACM","APP","PLTR","SBC"]
for per in ("13mo","18mo","2y"):
    raw=yf.download(ts, period=per, interval="1d", group_by="ticker", auto_adjust=False, progress=False, threads=True)
    last=collections.Counter(str(raw[t].dropna(how="all").index[-1].date()) for t in ts)
    print(per, dict(last))
h=yf.Ticker("AAPL").history(period="18mo"); print("AAPL hist 18mo tail", [str(x.date()) for x in h.index[-4:]])
