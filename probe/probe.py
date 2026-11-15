import requests, yfinance as yf, json
def t(n,f):
    try: print("OK  ",n,"→",str(f())[:600])
    except Exception as e: print("FAIL",n,"→",repr(e)[:250])
def yh(s):
    h=yf.Ticker(s).history(period="5y"); return len(h), str(h.index[0].date()), h.tail(1)[["Open","High","Low","Close"]].round(3).values.tolist()
for s in ("^VIX","^TNX","^TYX","^FVX","2YY=F","^IRX","ZT=F","^VKOSPI","^KQ11","^KS200"): t("yf "+s, lambda s=s: yh(s))
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36","Referer":"https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"}
def krx():
    d={"bld":"dbms/MDC/STAT/standard/MDCSTAT00301","indIdx":"1","indIdx2":"300","strtDd":"20231101","endDd":"20261113","share":"2","money":"3","csvxls_isNo":"false"}
    r=requests.post("https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",data=d,headers=UA,timeout=60); return r.status_code, r.text[:400]
t("KRX VKOSPI",krx)
def naver():
    r=requests.get("https://m.stock.naver.com/api/index/VKOSPI/price?pageSize=5&page=1",headers=UA,timeout=30); return r.status_code, r.text[:300]
t("naver m api VKOSPI",naver)
def naver2():
    r=requests.get("https://api.stock.naver.com/chart/domestic/index/VKOSPI?periodType=dayCandle",headers=UA,timeout=30); return r.status_code, r.text[:300]
t("naver chart VKOSPI",naver2)
def naver3():
    r=requests.get("https://fchart.stock.naver.com/sise.nhn?symbol=VKOSPI&timeframe=day&count=5&requestType=0",headers=UA,timeout=30); return r.status_code, r.text[-400:]
t("naver fchart VKOSPI",naver3)
def inv():
    r=requests.get("https://api.investing.com/api/financialdata/historical/1086?start-date=2023-11-01&end-date=2026-11-13&time-frame=Daily&add-missing-rows=false",headers={**UA,"domain-id":"kr"},timeout=30); return r.status_code, r.text[:300]
t("investing api",inv)
