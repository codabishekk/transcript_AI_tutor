import os, http.cookiejar, sys
from playwright.sync_api import sync_playwright

os.chdir("backend")
user_data = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data,
        headless=True,
        channel="msedge",
        args=["--disable-gpu", "--no-sandbox"],
    )
    page = browser.pages[0]
    page.goto("https://www.youtube.com")

    cdp = page.context.new_cdp_session(page)
    result = cdp.send("Network.getAllCookies")
    cookies = result.get("cookies", [])

    yt_cookies = [c for c in cookies if "youtube" in c.get("domain", "")]
    print(f"Total YouTube cookies: {len(yt_cookies)}", flush=True)
    for c in yt_cookies:
        print(f"  {c['name']}", flush=True)

    names = [c["name"] for c in yt_cookies]
    if "LOGIN_INFO" in names or "SAPISID" in names:
        print("\n*** LOGGED IN ***", flush=True)
        jar = http.cookiejar.MozillaCookieJar("cookies.txt")
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
        print("Saved to cookies.txt", flush=True)
    else:
        print("\n*** NOT LOGGED IN - no auth cookies ***", flush=True)

    browser.close()
