import base64
import os
import re
import tempfile
import time
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

DEPLOY_MARKER = "worker-rotate-v11"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Hard ceiling for /process so it always returns a JSON (CORS-enabled)
# response before Cloudflare's proxy in front of Render 502s. The gateway
# gives up well under 30s, so keep this comfortably below that.
PROCESS_DEADLINE_SECONDS = 8.0

# Deadline budget shared across the transcript-fetch request (set per request,
# checked before each slow fallback). Requests longer than this are aborted
# with a friendly timed_out error instead of a proxy 502.
_DEADLINE_AT = None


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


DEFAULT_WORKER_URLS = [
    "https://transcript-proxy.abishekkc923.workers.dev",
    "https://transcript-proxy-2.abishekkc923.workers.dev",
    "https://transcript-proxy-3.abishekkc923.workers.dev",
]


def _clean_proxy_entry(entry):
    """Trim an env entry and strip a stray 'TRANSCRIPT_PROXY=...' prefix so a
    misconfigured dashboard value (name pasted into the value) still parses."""
    entry = entry.strip().strip("'\"").rstrip("/")
    entry = re.sub(r"^[A-Za-z0-9_]+=", "", entry)
    return entry


def _proxy_url():
    raw = os.getenv("TRANSCRIPT_PROXY", "")
    urls = [_clean_proxy_entry(u) for u in raw.split(",")]
    urls = [u for u in urls if u]
    # If no plain (non-Worker) proxy is configured, fall back to the default
    # redundancy set so rotation across the extra Workers engages even when the
    # dashboard env var holds a single/misconfigured URL.
    if not any(not _is_worker_url(u) for u in urls):
        for d in DEFAULT_WORKER_URLS:
            if d not in urls:
                urls.append(d)
    return urls


def _is_worker_url(proxy_url):
    return bool(proxy_url) and "workers.dev" in proxy_url


def _worker_urls():
    return [u for u in _proxy_url() if _is_worker_url(u)]


def _describe_raw_error(err):
    if err is None:
        return "unknown"
    text = str(err).strip()
    return text or "unknown"


def _build_proxy_config():
    proxies = [u for u in _proxy_url() if not _is_worker_url(u)]
    proxy_url = proxies[0] if proxies else None
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
    proxy_urls = [u for u in _proxy_url() if not _is_worker_url(u)]
    proxy_url = proxy_urls[0] if proxy_urls else None
    if proxy_url:
        ydl_opts["proxy"] = proxy_url
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


BOT_CHECK_MARKERS = (
    "not a bot",
    "unusual traffic",
    "too many requests",
    "sign in to confirm",
    "sign-in to confirm",
)

AUTH_ERROR_MARKERS = (
    "sign in",
    "sign-in",
    "log in",
    "login",
    "logged in",
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


# Internal signal that the /process deadline elapsed. Raised by the deadline
# checks and deliberately NOT caught by the broad per-fallback except handlers,
# so a slow request aborts and returns JSON instead of hanging into a 502.
class _DeadlineExceeded(Exception):
    pass


def _check_deadline():
    if _DEADLINE_AT is not None and time.monotonic() > _DEADLINE_AT:
        raise _DeadlineExceeded()


def _cookies_configured():
    if os.getenv("YT_DLP_COOKIES_BASE64") or os.getenv("YT_DLP_COOKIES_TEXT"):
        return True
    cookie_path = resolve_cookiefile_path()
    return bool(cookie_path and os.path.isfile(cookie_path) and os.path.getsize(cookie_path) > 0)


def _describe_failure(api_error, yt_error):
    yt_msg = _describe_raw_error(yt_error)
    api_msg = str(api_error) if api_error else ""
    combined = f"{api_msg}\n{yt_msg}"

    if isinstance(api_error, (RequestBlocked, IpBlocked)) or _has_marker(
        combined, BOT_CHECK_MARKERS + ("blocked",)
    ):
        if os.getenv("TRANSCRIPT_PROXY"):
            return (
                "YouTube is blocking requests even through the configured proxies. "
                "Try different proxies or update your cookies.",
                "ip_blocked",
            )
        return (
            "YouTube blocks transcript requests from cloud server IPs. "
            "Deploy the Cloudflare Worker in proxy/ (free) and set TRANSCRIPT_PROXY "
            "to its URL on Render, or run the app locally.",
            "ip_blocked",
        )

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

    if isinstance(api_error, VideoUnavailable):
        return "the video is unavailable (private, removed, or deleted).", "video_unavailable"

    return yt_msg, "unknown"


def fetch_transcript_worker(video_id, timeout=15, retries=1, backoff=1.5):
    worker_urls = _worker_urls()
    if not worker_urls:
        raise Exception("No Worker URL configured")
    last_error = None
    order = list(worker_urls)

    # Fast single scan across every Worker (distinct egresses). Keep the
    # per-request timeout short and stop the moment the /process deadline is
    # reached so we never run past the gateway's patience.
    for worker_url in order:
        _check_deadline()
        try:
            resp = _requests.get(f"{worker_url}?v={video_id}", timeout=timeout)
        except Exception as e:
            last_error = e
            continue
        try:
            data = resp.json()
        except Exception as e:
            last_error = e
            continue
        if data.get("ok") and data.get("text"):
            return data["text"]
        last_error = Exception(data.get("error") or "Worker returned no transcript")

    # Pass 2: one brief retry round for IPs that may have recovered.
    for worker_url in order:
        _check_deadline()
        try:
            resp = _requests.get(f"{worker_url}?v={video_id}", timeout=timeout)
            data = resp.json()
        except Exception:
            continue
        if data.get("ok") and data.get("text"):
            return data["text"]

    _check_deadline()
    raise last_error or Exception("Worker returned no transcript")


def fetch_transcript_invidious(video_id):
    INVIDIOUS_INSTANCES = [
        "https://inv.nadeko.net",
        "https://iv.datura.network",
        "https://invidious.lunar.icu",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    non_worker = [u for u in _proxy_url() if not _is_worker_url(u)]
    proxy_url = non_worker[0] if non_worker else None
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
        proxy_urls = _proxy_url()
        worker_configured = bool(_worker_urls())

        # Worker mode: try the Cloudflare Workers API first (rotating across
        # each configured Worker) â€” they return the transcript directly and are
        # the intended path when configured.
        if worker_configured:
            try:
                return fetch_transcript_worker(video_id)
            except Exception as e:
                api_error = e
                # Fall through to the standard stack (cookies -> yt-dlp ->
                # Invidious) if all Workers fail, so a broken/unreachable
                # Worker doesn't hard-block processing.
                _check_deadline()
                return _fetch_via_stack(video_id, resolved_cookie, api_error)

        # Try youtube-transcript-api with the plain ANDROID client (no
        # cookies) first â€” stale cookies from cloud IPs can trigger a
        # bot-check, while the anonymous client often succeeds.
        api_error = None
        _check_deadline()
        try:
            return fetch_transcript_api(video_id, cookiefile=None)
        except Exception as e:
            api_error = e

        if resolved_cookie:
            _check_deadline()
            try:
                return fetch_transcript_api(video_id, cookiefile=resolved_cookie)
            except Exception as e:
                api_error = e

        # Fall back to yt-dlp with cookies for restricted videos
        yt_error = None
        _check_deadline()
        try:
            return fetch_transcript_ytdlp(video_id, cookiefile=resolved_cookie)
        except Exception as e:
            yt_error = e

        # Fall back to Invidious API (bypasses IP blocks via third-party proxies)
        _check_deadline()
        try:
            return fetch_transcript_invidious(video_id)
        except Exception:
            pass

        _check_deadline()
        message, code = _describe_failure(api_error, yt_error)
        raise TranscriptFetchError(message, code) from yt_error
    finally:
        if cookie_file and os.path.isfile(cookie_file):
            os.remove(cookie_file)


def _fetch_via_stack(video_id, resolved_cookie, worker_error=None):
    """Try the full fallback stack, reporting the most useful error."""
    api_error = None
    # First try the plain ANDROID client with no cookies â€” YouTube can
    # bot-check cookied sessions from cloud IPs, while an anonymous
    # ANDROID client request often still succeeds.
    _check_deadline()
    try:
        return fetch_transcript_api(video_id, cookiefile=None)
    except Exception as e:
        api_error = e

    if resolved_cookie:
        _check_deadline()
        try:
            return fetch_transcript_api(video_id, cookiefile=resolved_cookie)
        except Exception as e:
            api_error = e

    yt_error = None
    _check_deadline()
    try:
        return fetch_transcript_ytdlp(video_id, cookiefile=resolved_cookie)
    except Exception as e:
        yt_error = e

    _check_deadline()
    try:
        return fetch_transcript_invidious(video_id)
    except Exception:
        pass

    _check_deadline()
    if api_error is None and yt_error is None:
        api_error = worker_error
    message, code = _describe_failure(api_error, yt_error)
    raise TranscriptFetchError(message, code) from (yt_error or api_error)


@app.route("/process", methods=["POST"])
def process():
    global _DEADLINE_AT

    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "YouTube URL is required"}), 400

    video_id = extract_video_id(url)

    # YouTube throttling of datacenter/Cloudflare IPs is intermittent and often
    # recovers within a second, so retry transient failures a couple of times
    # before surfacing an error. A hard overall budget (below the gateway
    # timeout) guarantees we never hang into a 502 / bogus CORS error.
    _RETRIABLE = {"timed_out", "ip_blocked"}
    transcript = None
    last_code = "unknown"
    last_msg = "Unknown error"
    overall_start = time.monotonic()
    attempts = 0
    max_attempts = 3

    while attempts < max_attempts:
        attempts += 1
        # Keep the whole loop under the Cloudflare gateway (~30s) limit so
        # /process always returns JSON before it gives up (gunicorn is now set
        # to 240s, so the gateway is the binding constraint). 22s leaves margin
        # even when a blocking fallback call overruns its per-attempt deadline.
        remaining = overall_start + 22.0 - time.monotonic()
        if remaining <= 0:
            break
        _DEADLINE_AT = time.monotonic() + min(remaining, PROCESS_DEADLINE_SECONDS)

        try:
            transcript = fetch_transcript(video_id)
            break
        except _DeadlineExceeded:
            last_code = "timed_out"
            last_msg = "Fetching the transcript took too long. Please try again later."
        except TranscriptFetchError as e:
            last_code = e.code
            last_msg = str(e)
        except Exception as e:
            last_code = "unknown"
            last_msg = str(e)
        finally:
            _DEADLINE_AT = None

        if last_code not in _RETRIABLE or attempts >= max_attempts:
            break
        time.sleep(1.0)

    if transcript is None:
        if last_code == "timed_out":
            return jsonify({"error": last_msg, "error_code": "timed_out"}), 504
        return jsonify({
            "error": f"Failed to fetch transcript: {last_msg}",
            "error_code": last_code,
        }), 500

    try:
        process_video(url, transcript)
        return jsonify({"message": "Transcript processed successfully"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to process transcript: {str(e)}", "error_code": "processing_error"}), 500


@app.route("/debug/process_test")
def debug_process_test():
    import io
    import traceback

    video_id = request.args.get("video_id", "jNQXAC9IVRw")
    buf = io.StringIO()
    t = None
    try:
        t = fetch_transcript(video_id)
        buf.write(f"fetch_transcript OK ({len(t)} chars)\n")
    except Exception as e:
        buf.write(f"fetch_transcript FAILED: {e!r}\n")
        traceback.print_exc(file=buf)
    if t:
        try:
            process_video("https://www.youtube.com/watch?v=" + video_id, t)
            buf.write("process_video OK\n")
        except Exception as e:
            buf.write(f"process_video FAILED: {e!r}\n")
            traceback.print_exc(file=buf)
    text = buf.getvalue()
    try:
        with open(os.path.join(BASE_DIR, "debug_trace.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
    return text.replace("\n", "<br>"), 200


@app.route("/debug/trace")
def debug_trace():
    path = os.path.join(BASE_DIR, "debug_trace.txt")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read().replace("\n", "<br>"), 200
    return "no trace file", 200


@app.errorhandler(Exception)
def _debug_capture_unhandled(err):
    import traceback

    tb = traceback.format_exc()
    try:
        with open(os.path.join(BASE_DIR, "debug_trace.txt"), "w", encoding="utf-8") as f:
            f.write(tb)
    except Exception:
        pass
    return tb.replace("\n", "<br>"), 500


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
    info["transcript_proxy"] = os.getenv("TRANSCRIPT_PROXY", "")
    info["worker_urls"] = _worker_urls()
    info["is_worker_proxy"] = bool(_worker_urls())
    info["deploy_marker"] = DEPLOY_MARKER
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
