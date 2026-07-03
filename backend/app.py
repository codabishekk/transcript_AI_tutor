import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi

from rag import process_video, ask_question

app = Flask(__name__)
CORS(app)

@app.route("/process", methods=["POST"])
def process():

    data = request.json
    url = data.get("url")
    transcript = data.get("transcript")

    if not url:
        return jsonify({"error": "YouTube URL is required"}), 400

    if not transcript:
        try:
            video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
            fetched = YouTubeTranscriptApi().fetch(video_id)
            transcript = " ".join(snippet.text for snippet in fetched.snippets)
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