r"""Extract decrypted YouTube/Google cookies directly from a running browser
via the Chrome DevTools Protocol (CDP).

Because modern Chrome/Edge encrypt cookie values with app-bound encryption
(DPAPI) that yt-dlp cannot decrypt, we instead read cookies straight from the
browser over CDP, which returns already-decrypted cookie values.

Usage:
    1. Close all browser windows.
    2. Relaunch Edge with remote debugging enabled:
         msedge --remote-debugging-port=9222 --user-data-dir="C:\edge-debug"
       (and log into YouTube in that window)
    3. Run:  python get_cookies_cdp.py
       It prints the Netscape cookies.txt content and the base64 value to set
       as YT_DLP_COOKIES_BASE64 / to commit as backend/cookies.txt.
"""

import argparse
import base64
import json
import time
import urllib.request
from http.cookiejar import Cookie

CDP_HTTP = "http://127.0.0.1:9222"


def get_tabs():
    with urllib.request.urlopen(f"{CDP_HTTP}/json", timeout=5) as r:
        return json.load(r)


def cdp_ws_url():
    for tab in get_tabs():
        if tab.get("type") == "page":
            return tab["webSocketDebuggerUrl"]
    raise RuntimeError("No open page tab found. Open a tab then re-run.")


class CDP:
    def __init__(self, ws_url):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        self.ws.send(json.dumps({
            "id": self._id,
            "method": method,
            "params": params or {},
        }))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                return msg.get("result", {})
            if msg.get("method") == "Network.cookieChanged" and msg.get("params", {}).get("removed"):
                pass


def fetch_cookies():
    cdp = CDP(cdp_ws_url())
    cdp.call("Network.enable")
    result = cdp.call("Network.getAllCookies")
    cdp.ws.close()
    return result.get("cookies", [])


def to_netscape(cookies):
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c.get("domain", "")
        if not any(d in domain for d in (".youtube.com", ".google.com", ".ytimg.com")):
            continue
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        expires = int(c.get("expires", 0))
        if expires == -1:
            expires = 0
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append("\t".join([
            domain, include_subdomains, path, secure, str(expires), name, value,
        ]))
    return "\n".join(lines) + ("\n" if len(lines) > 1 else "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9222)
    args = parser.parse_args()
    global CDP_HTTP
    CDP_HTTP = f"http://127.0.0.1:{args.port}"

    for attempt in range(20):
        try:
            cookies = fetch_cookies()
            break
        except Exception as e:
            if attempt == 19:
                raise
            print(f"Waiting for browser CDP... {e}")
            time.sleep(2)

    netscape = to_netscape(cookies)
    b64 = base64.b64encode(netscape.encode("utf-8")).decode("ascii")
    print(netscape)
    print()
    print("--- BEGIN YT_DLP_COOKIES_BASE64 ---")
    print(b64)
    print("--- END YT_DLP_COOKIES_BASE64 ---")


if __name__ == "__main__":
    main()
