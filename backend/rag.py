import os
import time
import numpy as np
import faiss
import requests

from dotenv import load_dotenv

load_dotenv()

qa_state = None


def _chunk_text(text, chunk_size=1000, chunk_overlap=200):
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_size)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = max(start + 1, end - chunk_overlap)
    return chunks


def _get_api_key():
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set. Configure it in your environment before processing a video.")
    return api_key


def _request_with_retry(method, url, max_retries=3, **kwargs):
    """Make an HTTP request with exponential backoff on 429 errors."""
    for attempt in range(max_retries):
        response = method(url, **kwargs)
        if response.status_code == 429 and attempt < max_retries - 1:
            wait_time = 2 ** attempt * 5  # 5s, 10s, 20s
            print(f"Rate limited (429). Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
            time.sleep(wait_time)
            continue
        response.raise_for_status()
        return response
    response.raise_for_status()
    return response


def _embed_text(text):
    api_key = _get_api_key()
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text}]},
    }
    response = _request_with_retry(
        requests.post,
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}",
        json=payload,
        timeout=60,
    )
    data = response.json()
    return np.array(data["embedding"]["values"], dtype="float32")


def _generate_answer(prompt):
    api_key = _get_api_key()
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = _request_with_retry(
        requests.post,
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        json=payload,
        timeout=60,
    )
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        return "No answer generated."
    parts = candidates[0].get("content", {}).get("parts", [])
    text = parts[0].get("text", "") if parts else ""
    return text.strip() or "No answer generated."


def process_video(url, transcript):
    global qa_state

    if not transcript or not transcript.strip():
        raise ValueError("Transcript is empty")

    with open("transcript.txt", "w", encoding="utf-8") as f:
        f.write(transcript)

    chunks = _chunk_text(transcript)
    if not chunks:
        raise ValueError("Transcript is empty after chunking")

    embeddings = np.vstack([_embed_text(chunk) for chunk in chunks]).astype("float32")

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    qa_state = {
        "chunks": chunks,
        "index": index,
    }


def ask_question(question):
    global qa_state

    if qa_state is None:
        return "Please process a YouTube video first."

    if not question or not question.strip():
        return "Please provide a question."

    chunks = qa_state["chunks"]
    index = qa_state["index"]

    query_embedding = _embed_text(question)
    _, indices = index.search(np.array([query_embedding], dtype="float32"), min(4, len(chunks)))

    context_chunks = [chunks[int(idx)] for idx in indices[0] if 0 <= int(idx) < len(chunks)]
    if not context_chunks:
        return "I couldn't find relevant context in the transcript."

    context = "\n\n".join(context_chunks)
    prompt = (
        "You are a helpful assistant. Answer the user's question using only the provided transcript context. "
        "If the answer is not in the context, say that you do not know.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )

    return _generate_answer(prompt)