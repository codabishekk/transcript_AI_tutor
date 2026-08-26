##AI YouTube Tutor - Backend
Overview

The AI YouTube Tutor backend is a Flask-based REST API that powers the application's Retrieval-Augmented Generation (RAG) pipeline. It retrieves YouTube video transcripts, processes them into vector embeddings using Google's Gemini embedding model, stores them in a FAISS vector database, and answers user questions using Google's Gemini large language model.

##The backend exposes REST APIs that can be consumed by a React frontend or any other client application.

##Features
Fetch YouTube video transcripts
- Uses `youtube-transcript-api` first for public transcripts
- Falls back to `yt-dlp` when YouTube requires authentication
- Supports cookies via `backend/cookies.txt`, `YT_DLP_COOKIES_FILE`, `YT_DLP_COOKIES_TEXT`, or `YT_DLP_COOKIES_BASE64`
Generate embeddings using Google Gemini
Store embeddings in a FAISS vector database
Retrieval-Augmented Generation (RAG)
Question-answering over YouTube transcripts
RESTful API using Flask
Cross-Origin Resource Sharing (CORS) enabled for React frontend
Tech Stack
Python 3.10+
Flask
Flask-CORS
LangChain
Google Gemini API
FAISS
YouTube Transcript API
PyTube
python-dotenv

## Cookie setup (for videos that require sign-in)

Some videos (age-restricted, members-only, or "confirm you're not a bot" checks) only expose
captions to signed-in users. The backend fetches transcripts with `youtube-transcript-api` first
and falls back to `yt-dlp`, which can use YouTube cookies.

### Export cookies from your browser

1. Close your browser completely (check the system tray).
2. Run the export script (uses your logged-in YouTube session):

   ```
   cd backend
   .venv\Scripts\python.exe export_cookies.py
   ```

   By default it reads Edge; pass `--browser chrome` (or firefox/brave/vivaldi) to use another
   browser. The script writes `backend/cookies.txt` and prints a base64 value.

### Deploy to Render

1. In the Render dashboard open your service > Environment.
2. Add `YT_DLP_COOKIES_BASE64` with the value printed by the script (between the BEGIN/END markers).
3. Save and redeploy, then retry the video.

Alternatively set `YT_DLP_COOKIES_TEXT` (the raw Netscape-format cookie text) or
`YT_DLP_COOKIES_FILE` (path to a cookies file on the server). For local development you can also
place a `cookies.txt` file in `backend/`.

Note: session cookies expire. Re-run `export_cookies.py` and update the env var when transcripts
start failing again.
