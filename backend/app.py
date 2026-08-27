import base64
import os
import re
import tempfile
from http.cookiejar import MozillaCookieJar
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests as _requests
import yt_dlp
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    AgeRestricted,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
)

from rag import process_video, ask_question

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def extract_video_id(url):
    match = re.search(r"(?:v=|\/)([a-zA-Z0-9_-]{11})(?:[&?]|$)", url)
    return match.group(1) if match else url.split("/")[-1]


def resolve_cookiefile_path():
    env_path = os.getenv("YT_DLP_COOKIES_FILE")
    if env_path:
        return env_path
    return os.path.join(BASE_DIR, "cookies.txt")


COOKIE_HEADER = b"# Netscape HTTP Cookie File\n"


def _ensure_cookie_header(data):
    if isinstance(data, str):
        if not data.startswith("# Netscape"):
            return COOKIE_HEADER + data.encode("utf-8")
        return data.encode("utf-8")
    if isinstance(data, bytes):
        if not data.startswith(b"# Netscape"):
            return COOKIE_HEADER + data
        return data
    return data


def write_temp_cookies_from_base64(cookie_b64):
    if not cookie_b64:
        return None
    decoded = base64.b64decode(cookie_b64)
    decoded = _ensure_cookie_header(decoded)
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp_file.write(decoded)
    tmp_file.close()
    return tmp_file.name


def write_temp_cookies_from_text(cookie_text):
    if not cookie_text:
        return None
    data = _ensure_cookie_header(cookie_text)
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp_file.write(data)
    tmp_file.close()
    return tmp_file.name


def _build_proxy_config():
    proxy_url = os.getenv("TRANSCRIPT_PROXY")
    if not proxy_url:
        return None
    from youtube_transcript_api.proxies import GenericProxyConfig
    if proxy_url.startswith("socks"):
        return GenericProxyConfig(
            http_url=proxy_url,
            https_url=proxy_url,
        )
    return GenericProxyConfig(
        http_url=proxy_url,
        https_url=proxy_url,
    )


def fetch_transcript_api(video_id, cookiefile=None):
    http_client = None
    if cookiefile:
        jar = MozillaCookieJar(cookiefile)
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
        else:
            session = _requests.Session()
            session.cookies = jar
            http_client = session

    proxy_config = _build_proxy_config()
    try:
        if proxy_config:
            api = YouTubeTranscriptApi(proxy_config=proxy_config, http_client=http_client)
        elif http_client:
            api = YouTubeTranscriptApi(http_client=http_client)
        else:
            api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=["en", "en-orig"])
        return " ".join(snippet.text for snippet in transcript.snippets)
    except Exception:
        raise


def fetch_transcript_ytdlp(video_id, cookiefile=None):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-orig"],
        "geo_bypass": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
    }
    cookies_path = cookiefile or resolve_cookiefile_path()
    if cookies_path and os.path.isfile(cookies_path) and os.path.getsize(cookies_path) > 0:
        ydl_opts["cookiefile"] = cookies_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_id, download=False)
        subs = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        for lang in ["en", "en-orig"]:
            for source in (subs, auto):
                tracks = source.get(lang)
                if tracks:
                    for track in tracks:
                        sub_url = track.get("url")
                        if sub_url:
                            resp = _requests.get(sub_url, headers=ydl_opts["http_headers"], timeout=30)
                            if resp.ok:
                                text = re.sub(r"<[^>]+>", "", resp.text)
                                return re.sub(r"\s+", " ", text).strip()
    raise Exception("No English transcript available")


AUTH_ERROR_MARKERS = (
    "sign in",
    "sign-in",
    "log in",
    "login",
    "logged in",
    "not a bot",
    "age-restricted",
    "age restricted",
    "members-only",
    "members only",
    "membership",
    "requires authentication",
    "authentication",
)

NO_TRANSCRIPT_MARKERS = (
    "no subtitles",
    "no video subtitles",
    "no transcript",
    "no captions",
    "subtitles are disabled",
    "no automatic captions",
    "no timed captions",
)


def _has_marker(message, markers):
    lowered = message.lower()
    return any(marker in lowered for marker in markers)


class TranscriptFetchError(Exception):
    def __init__(self, message, code="unknown"):
        super().__init__(message)
        self.code = code


def _cookies_configured():
    if os.getenv("YT_DLP_COOKIES_BASE64") or os.getenv("YT_DLP_COOKIES_TEXT"):
        return True
    cookie_path = resolve_cookiefile_path()
    return bool(cookie_path and os.path.isfile(cookie_path) and os.path.getsize(cookie_path) > 0)


def _describe_failure(api_error, yt_error):
    yt_msg = str(yt_error)
    api_msg = str(api_error) if api_error else ""
    combined = f"{api_msg}\n{yt_msg}"

    if isinstance(api_error, AgeRestricted) or _has_marker(combined, AUTH_ERROR_MARKERS):
        if _cookies_configured():
            return (
                "the video requires authentication, but the configured YouTube cookies are "
                "invalid or expired. Export fresh cookies with backend/export_cookies.py and "
                "update YT_DLP_COOKIES_BASE64 on the server.",
                "auth_required",
            )
        return (
            "this video requires you to be signed in to YouTube (or is age-restricted). "
            "Export your YouTube cookies by running backend/export_cookies.py and set the "
            "YT_DLP_COOKIES_BASE64 env var on the server (for local development, place the "
            "generated cookies.txt in backend/), then retry. "
            "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp",
            "auth_required",
        )

    if isinstance(api_error, (NoTranscriptFound, TranscriptsDisabled)) or _has_marker(
        yt_msg, NO_TRANSCRIPT_MARKERS
    ):
        return "no English transcript or captions were found for this video.", "no_transcript"

    if isinstance(api_error, (RequestBlocked, IpBlocked)) or "blocked" in yt_msg.lower():
        if os.getenv("TRANSCRIPT_PROXY"):
            return (
                "YouTube is blocking requests even through the configured proxy. "
                "Try a different proxy or update your cookies.",
                "ip_blocked",
            )
        return (
            "YouTube blocks transcript requests from cloud server IPs. "
            "Deploy the Cloudflare Worker in proxy/ (free) and set TRANSCRIPT_PROXY "
            "to its URL on Render, or run the app locally.",
            "ip_blocked",
        )

    if isinstance(api_error, VideoUnavailable):
        return "the video is unavailable (private, removed, or deleted).", "video_unavailable"

    return yt_msg, "unknown"


def fetch_transcript_worker(video_id):
    proxy_url = os.getenv("TRANSCRIPT_PROXY", "").rstrip("/")
    worker_url = f"{proxy_url}?v={video_id}" if proxy_url else None
    if not worker_url:
        raise Exception("No Worker URL configured")
    resp = _requests.get(worker_url, timeout=30)
    data = resp.json()
    if data.get("ok") and data.get("text"):
        return data["text"]
    raise Exception(data.get("error") or "Worker returned no transcript")


def _is_worker_url(proxy_url):
    return proxy_url and "workers.dev" in proxy_url


def fetch_transcript_invidious(video_id):
    INVIDIOUS_INSTANCES = [
        "https://inv.nadeko.net",
        "https://iv.datura.network",
        "https://invidious.lunar.icu",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    proxy_url = os.getenv("TRANSCRIPT_PROXY")
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    for instance in INVIDIOUS_INSTANCES:
        try:
            captions_url = f"{instance}/api/v1/captions/{video_id}"
            resp = _requests.get(captions_url, headers=headers, timeout=5, proxies=proxies)
            if not resp.ok:
                continue
            captions = resp.json().get("captions", [])

            label = None
            for cap in captions:
                lang = cap.get("languageCode") or cap.get("language_code", "")
                if lang in ("en", "en-US", "en-orig"):
                    label = cap.get("label")
                    break
            if not label and captions:
                label = captions[0].get("label")

            if not label:
                continue

            sub_url = f"{instance}/api/v1/captions/{video_id}?label={label}"
            sub_resp = _requests.get(sub_url, headers=headers, timeout=5, proxies=proxies)
            if sub_resp.ok and sub_resp.text.strip():
                text = re.sub(r"<[^>]+>", "", sub_resp.text)
                return re.sub(r"\s+", " ", text).strip()
        except Exception:
            continue

    raise Exception("No English transcript available via Invidious")


def fetch_transcript(video_id):
    cookie_b64 = os.getenv("YT_DLP_COOKIES_BASE64")
    cookie_text = os.getenv("YT_DLP_COOKIES_TEXT")
    cookie_file = None

    if cookie_b64:
        cookie_file = write_temp_cookies_from_base64(cookie_b64)
    elif cookie_text:
        cookie_file = write_temp_cookies_from_text(cookie_text)

    resolved_cookie = cookie_file or resolve_cookiefile_path()
    if resolved_cookie and (not os.path.isfile(resolved_cookie) or os.path.getsize(resolved_cookie) == 0):
        resolved_cookie = None

    try:
        # Try youtube-transcript-api first (with cookies when available)
        api_error = None
        try:
            return fetch_transcript_api(video_id, cookiefile=resolved_cookie)
        except Exception as e:
            api_error = e

        # Fall back to yt-dlp with cookies for restricted videos
        yt_error = None
        try:
            return fetch_transcript_ytdlp(video_id, cookiefile=resolved_cookie)
        except Exception as e:
            yt_error = e

        # If TRANSCRIPT_PROXY points to a Cloudflare Worker, call its API directly
        proxy_url = os.getenv("TRANSCRIPT_PROXY", "")
        if _is_worker_url(proxy_url):
            try:
                return fetch_transcript_worker(video_id)
            except Exception:
                pass

        # Fall back to Invidious API (bypasses IP blocks via third-party proxies)
        try:
            return fetch_transcript_invidious(video_id)
        except Exception:
            pass

        message, code = _describe_failure(api_error, yt_error)
        raise TranscriptFetchError(message, code) from yt_error
    finally:
        if cookie_file and os.path.isfile(cookie_file):
            os.remove(cookie_file)

@app.route("/process", methods=["POST"])
def process():

    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "YouTube URL is required"}), 400

    try:
        video_id = extract_video_id(url)
        transcript = fetch_transcript(video_id)
    except TranscriptFetchError as e:
        return jsonify({"error": f"Failed to fetch transcript: {str(e)}", "error_code": e.code}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to fetch transcript: {str(e)}", "error_code": "unknown"}), 500

    try:
        process_video(url, transcript)
        return jsonify({"message": "Transcript processed successfully"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to process transcript: {str(e)}", "error_code": "processing_error"}), 500


@app.route("/ask", methods=["POST"])
def ask():

    data = request.json
    question = data.get("question")

    if not question:
        return jsonify({"error": "Question required"}), 400

    try:
        answer = ask_question(question)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": f"Failed to generate answer: {str(e)}"}), 500


@app.route("/debug/cookies")
def debug_cookies():
    info = {}
    info["BASE_DIR"] = BASE_DIR
    info["cookie_file_path"] = resolve_cookiefile_path()
    cookie_path = resolve_cookiefile_path()
    info["file_exists"] = os.path.isfile(cookie_path) if cookie_path else False
    info["file_size"] = os.path.getsize(cookie_path) if cookie_path and os.path.isfile(cookie_path) else 0
    info["has_env_base64"] = bool(os.getenv("YT_DLP_COOKIES_BASE64"))
    info["has_env_text"] = bool(os.getenv("YT_DLP_COOKIES_TEXT"))
    info["has_env_file"] = bool(os.getenv("YT_DLP_COOKIES_FILE"))
    info["has_openrouter_key"] = bool(os.getenv("OPENROUTER_API_KEY"))
    info["has_transcript_proxy"] = bool(os.getenv("TRANSCRIPT_PROXY"))
    info["is_worker_proxy"] = _is_worker_url(os.getenv("TRANSCRIPT_PROXY", ""))
    if cookie_path and os.path.isfile(cookie_path):
        try:
            jar = MozillaCookieJar(cookie_path)
            jar.load(ignore_discard=True, ignore_expires=True)
            info["cookies_loaded"] = len(list(jar))
            info["cookie_names"] = sorted({c.name for c in jar})
        except Exception as e:
            info["cookie_load_error"] = str(e)
    return jsonify(info)


if __name__ == "__main__":
    app.run(debug=True)