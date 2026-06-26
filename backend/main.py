import os
from flask import Flask, request, jsonify
from flask_cors import CORS

from rag import process_video, ask_question

app = Flask(__name__)
CORS(app)

@app.route("/process", methods=["POST"])
def process():

    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "YouTube URL is required"}), 400

    try:
        process_video(url)
        return jsonify({"message": "Transcript processed successfully"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        question = data.get("question")
        if not question:
            return jsonify({"error": "Question required"}), 400
        answer = ask_question(question)
        return jsonify({"answer": answer})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)