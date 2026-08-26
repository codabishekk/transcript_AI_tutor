import argparse
import base64
import os
import sqlite3
import sys
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import yt_dlp.cookies as yt_cookies
from yt_dlp.cookies import extract_cookies_from_browser
from yt_dlp.utils import DownloadError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOGIN_COOKIES = {"LOGIN_INFO", "SAPISID", "__Secure-3PAPISID", "SIDCC", "HSID"}

_original_open_database_copy = yt_cookies._open_database_copy


class CookieExportError(Exception):
    pass


def _open_database_copy_robust(database_path, tmpdir):
    """Copy the browser cookie DB even if the browser holds a lock on it.

    yt-dlp's default copy uses shutil.copy, which fails with a PermissionError
    when the browser (e.g. Edge) is running and the SQLite database is locked.
    SQLite's online backup API can read a database that is in use, so we fall
    back to that when the plain copy fails.
    """
    try:
        return _original_open_database_copy(database_path, tmpdir)
    except PermissionError:
        pass

    database_copy_path = os.path.join(tmpdir, "temporary.sqlite")
    try:
        src = sqlite3.connect(f"{Path(database_path).as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        raise CookieExportError(
            f"Could not read the browser cookie database at {database_path}. "
            "Close the browser completely (check the system tray) and re-run this script."
        ) from e
    try:
        dst = sqlite3.connect(database_copy_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return sqlite3.connect(database_copy_path).cursor()


yt_cookies._open_database_copy = _open_database_copy_robust


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Export your logged-in YouTube cookies for the transcript app. "
            "Use this on Render/cloud hosts so videos that require sign-in can be processed."
        )
    )
    parser.add_argument(
        "--browser",
        default="edge",
        choices=["edge", "chrome", "firefox", "brave", "opera", "vivaldi", "chromium"],
        help="Browser that is logged in to YouTube (default: edge).",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Browser profile to use (defaults to the browser's default profile).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"Where to write the cookies file (default: {os.path.join(BASE_DIR, 'cookies.txt')}).",
    )
    args = parser.parse_args()

    try:
        jar = extract_cookies_from_browser(args.browser, profile=args.profile)
    except CookieExportError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (DownloadError, PermissionError, sqlite3.OperationalError) as e:
        print(
            f"Error: could not copy the {args.browser} cookie database ({e}). "
            "Close the browser completely (check the system tray / background processes) "
            "and re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error reading cookies from {args.browser}: {e}", file=sys.stderr)
        print("Make sure the browser is installed and you are logged in to YouTube.", file=sys.stderr)
        sys.exit(1)

    yt = MozillaCookieJar()
    for cookie in jar:
        domain = cookie.domain or ""
        if "youtube" in domain or "google" in domain:
            yt.set_cookie(cookie)

    names = {c.name for c in yt}
    has_login = bool(names & LOGIN_COOKIES)

    out_path = args.out or os.path.join(BASE_DIR, "cookies.txt")
    yt.save(out_path, ignore_discard=True, ignore_expires=True)

    with open(out_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    print(f"Exported {len(yt)} YouTube cookies to {out_path}")
    if not has_login:
        print(
            "WARNING: No login cookies found (LOGIN_INFO/SAPISID). "
            "Log in to YouTube in your browser first, then re-run.",
            file=sys.stderr,
        )

    print()
    print("=== Render setup ===")
    print("1. Open your Render dashboard > your service > Environment.")
    print("2. Add an environment variable:")
    print("   Name:  YT_DLP_COOKIES_BASE64")
    print("   Value: the text between the BEGIN/END markers below")
    print()
    print("--- BEGIN YT_DLP_COOKIES_BASE64 ---")
    print(b64)
    print("--- END YT_DLP_COOKIES_BASE64 ---")
    print()
    print("3. Save and redeploy, then retry the video.")
    print("Note: cookies expire. Re-run this script and update the value when they stop working.")


if __name__ == "__main__":
    main()
