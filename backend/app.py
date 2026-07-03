import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp

from rag import process_video, ask_question

app = Flask(__name__)
CORS(app)

def extract_video_id(url):
    match = re.search(r"(?:v=|\/)([a-zA-Z0-9_-]{11})(?:[&?]|$)", url)
    return match.group(1) if match else url.split("/")[-1]

def fetch_transcript_ytdlp(video_id):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
    }
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

@app.route("/process", methods=["POST"])
def process():

    data = request.json
    url = data.get("url")
    transcript = data.get("transcript")

    if not url:
        return jsonify({"error": "YouTube URL is required"}), 400

    if not transcript:
        try:
            video_id = extract_video_id(url)
            transcript = fetch_transcript_ytdlp(video_id)
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

    answer = ask_question(question)

    return jsonify({
        "answer": answer
    })


if __name__ == "__main__":
    app.run(debug=True)