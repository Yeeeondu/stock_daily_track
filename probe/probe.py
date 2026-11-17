import os, json, requests
k = os.environ.get("KRX_API_KEY", "")
print("key present:", bool(k), "len", len(k))
for d in ("20261117", "20261113"):
    for path in ("idx/drvprod_dd_trd", "idx/kospi_dd_trd"):
        try:
            r = requests.get(f"https://data-dbg.krx.co.kr/svc/apis/{path}", params={"basDd": d}, headers={"AUTH_KEY": k}, timeout=30)
            print(path, d, r.status_code, r.text[:200].replace("\n", " "))
            j = r.json(); rows = j.get("OutBlock_1") or []
            print("  rows", len(rows), "keys", list(rows[0].keys()) if rows else None)
            for x in rows:
                if "변동성" in str(x.get("IDX_NM", "")) or "VKOSPI" in str(x).upper():
                    print("  VK:", x)
        except Exception as e:
            print("FAIL", path, d, repr(e)[:200])
