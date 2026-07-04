import base64
import os
import re
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp

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


def write_temp_cookies_from_base64(cookie_b64):
    if not cookie_b64:
        return None
    decoded = base64.b64decode(cookie_b64)
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp_file.write(decoded)
    tmp_file.close()
    return tmp_file.name


def write_temp_cookies_from_text(cookie_text):
    if not cookie_text:
        return None
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp_file.write(cookie_text.encode("utf-8"))
    tmp_file.close()
    return tmp_file.name


def fetch_transcript_ytdlp(video_id, cookiefile=None):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
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
                            import requests
                            resp = requests.get(sub_url)
                            if resp.ok:
                                text = re.sub(r"<[^>]+>", "", resp.text)
                                return re.sub(r"\s+", " ", text).strip()
    raise Exception("No English transcript available")


def fetch_transcript(video_id):
    cookie_b64 = os.getenv("YT_DLP_COOKIES_BASE64")
    cookie_text = os.getenv("YT_DLP_COOKIES_TEXT")
    cookie_file = None

    if cookie_b64:
        cookie_file = write_temp_cookies_from_base64(cookie_b64)
    elif cookie_text:
        cookie_file = write_temp_cookies_from_text(cookie_text)

    try:
        return fetch_transcript_ytdlp(video_id, cookiefile=cookie_file)
    except Exception as yt_error:
        cookie_path = resolve_cookiefile_path()
        if cookie_path and os.path.isfile(cookie_path) and os.path.getsize(cookie_path) > 0:
            raise Exception(
                f"Failed to fetch transcript using yt-dlp with cookies at {cookie_path}. "
                "Make sure the file contains valid YouTube session cookies. "
                "See https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
            ) from yt_error
        raise Exception(
            "Failed to fetch transcript. Some YouTube videos require authentication. "
            "Export YouTube cookies to backend/cookies.txt or set YT_DLP_COOKIES_FILE or YT_DLP_COOKIES_TEXT. "
            "You can also set YT_DLP_COOKIES_BASE64 with base64-encoded cookies content. "
            "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
        ) from yt_error
    finally:
        if cookie_file and os.path.isfile(cookie_file):
            os.remove(cookie_file)

@app.route("/process", methods=["POST"])
def process():

    data = request.json
    url = data.get("url")
    transcript = data.get("transcript")

    if not url and not transcript:
        return jsonify({"error": "YouTube URL or transcript is required"}), 400

    if not transcript and url:
        try:
            video_id = extract_video_id(url)
            transcript = fetch_transcript(video_id)
        except Exception as e:
            return jsonify({"error": f"Failed to fetch transcript: {str(e)}"}), 500

    try:
        process_video(url, transcript)
        return jsonify({"message": "Transcript processed successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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


if __name__ == "__main__":
    app.run(debug=True)