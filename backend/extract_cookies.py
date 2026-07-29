import subprocess, time, json, os, http.cookiejar
import urllib.request, websocket

edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
user_data = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")

cmd = [
    edge_path,
    f"--user-data-dir={user_data}",
    "--remote-debugging-port=9222",
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "https://www.youtube.com",
]
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(5)

try:
    resp = urllib.request.urlopen("http://127.0.0.1:9222/json")
    targets = json.loads(resp.read())
    ws_url = targets[0]["webSocketDebuggerUrl"]

    ws = websocket.create_connection(ws_url)
    ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
    resp = json.loads(ws.recv())
    cookies = resp.get("result", {}).get("cookies", [])
    ws.close()

    yt_cookies = [c for c in cookies if "youtube" in c.get("domain", "")]
    print(f"Got {len(yt_cookies)} YouTube cookies")
    for c in yt_cookies:
        print(f"  {c['name']}")

    names = [c["name"] for c in yt_cookies]
    if "LOGIN_INFO" in names or "SAPISID" in names:
        print("\n*** LOGGED IN ***")
        jar = http.cookiejar.MozillaCookieJar("backend/cookies.txt")
        for c in yt_cookies:
            jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0, name=c["name"], value=c["value"],
                    port=None, port_specified=False,
                    domain=c["domain"], domain_specified=True,
                    domain_initial_dot=c["domain"].startswith("."),
                    path=c["path"], path_specified=True,
                    secure=c.get("secure", False),
                    expires=int(c.get("expires", 0)) if c.get("expires") else 0,
                    discard=False, comment=None, comment_url=None,
                    rest={"HttpOnly": c.get("httpOnly", False)},
                )
            )
        jar.save(ignore_discard=True, ignore_expires=True)
        print("Saved cookies")
    else:
        print("\n*** NOT LOGGED IN - no auth cookies ***")

finally:
    proc.terminate()
    time.sleep(1)
