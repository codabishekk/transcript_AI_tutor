import os
import time
import numpy as np
import requests

from dotenv import load_dotenv
from fastembed import TextEmbedding

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
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        # Fallback to GOOGLE_API_KEY for backward compatibility
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Configure it in your environment before processing a video.")
    return api_key


def _request_with_retry(method, url, max_retries=3, retry_statuses=(429,), **kwargs):
    last_response = None
    for attempt in range(max_retries):
        response = method(url, **kwargs)
        last_response = response
        if response.status_code in retry_statuses and attempt < max_retries - 1:
            wait_time = 2 ** attempt * 5
            print(f"Model unavailable ({response.status_code}). Retrying in {wait_time}s "
                  f"(attempt {attempt + 1}/{max_retries})...")
            time.sleep(wait_time)
            continue
        response.raise_for_status()
        return response
    last_response.raise_for_status()
    return last_response


_model = None


def _get_model():
    global _model
    if _model is None:
        _model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return _model


def _embed_text(text):
    model = _get_model()
    embedding = next(model.embed(text))
    return np.array(embedding, dtype="float32")


_MODELS = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "z-ai/glm-5.2:free",
    "minimax/minimax-m3:free",
)


def _generate_answer(prompt):
    api_key = _get_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}
    url = "https://openrouter.ai/api/v1/chat/completions"
    last_err = None
    for model in _MODELS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response = _request_with_retry(
                requests.post, url, json=payload, headers=headers, timeout=60
            )
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return "No answer generated."
            content = choices[0].get("message", {}).get("content", "").strip()
            if content:
                return content
            return "No answer generated."
        except Exception as e:
            last_err = e
            print(f"Model {model} failed ({e}); trying fallback.")
    raise last_err


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

    qa_state = {
        "chunks": chunks,
        "embeddings": embeddings,
    }


def ask_question(question):
    global qa_state

    if qa_state is None:
        return "Please process a YouTube video first."

    if not question or not question.strip():
        return "Please provide a question."

    chunks = qa_state["chunks"]
    embeddings = qa_state["embeddings"]

    query_embedding = _embed_text(question)

    # Cosine similarity search (replaces FAISS for Windows compatibility)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    query_norm = np.linalg.norm(query_embedding)
    similarities = (embeddings @ query_embedding) / (norms.flatten() * query_norm + 1e-10)
    k = min(4, len(chunks))
    top_indices = np.argsort(similarities)[-k:][::-1]

    context_chunks = [chunks[int(idx)] for idx in top_indices]
    if not context_chunks:
        return "I couldn't find relevant context in the transcript."

    context = "\n\n".join(context_chunks)
    prompt = (
        "You are a helpful assistant. Answer the user's question using only the provided transcript context. "
        "If the answer is not in the context, say that you do not know.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )

    return _generate_answer(prompt)
