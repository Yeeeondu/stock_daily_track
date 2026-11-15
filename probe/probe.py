import requests
UA={"User-Agent":"Mozilla/5.0","Content-Type":"application/json"}
for n in range(10,160,10):
    obj=f"STATSCU01000{n:03d}0BO" if n<100 else f"STATSCU0100000{n}BO"
    obj=f"STATSCU0100000{n:03d}BO"
    try:
        r=requests.post("https://freesis.kofia.or.kr/meta/getMetaDataList.do",json={"dmSearch":{"tmpV40":"1000000","tmpV41":"1","tmpV1":"D","tmpV45":"20261101","tmpV46":"20261113","OBJ_NM":obj}},headers=UA,timeout=30)
        j=r.json(); ds=j.get("ds1")
        print("OK  ",obj, len(ds) if ds else None, (ds[0] if ds else str(j)[:150]))
    except Exception as e: print("FAIL",obj,repr(e)[:100])
