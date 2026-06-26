# AI YouTube Tutor 🚀

AI YouTube Tutor is a powerful web application that allows users to interact with any YouTube video using AI. By simply pasting a YouTube URL, the app extracts the transcript, processes it using a RAG (Retrieval-Augmented Generation) pipeline, and enables you to ask questions about the video's content.

## ✨ Features

- **Instant Transcript Processing**: Provide a YouTube URL and get the full content indexed in seconds.
- **AI-Powered Q&A**: Ask complex questions about the video and get accurate, context-aware answers.
- **RAG Architecture**: Uses Retrieval-Augmented Generation for factually grounded responses.
- **Modern UI**: Sleek, responsive interface built with React and custom CSS.

## 🛠️ Tech Stack

### Backend
- **Framework**: Flask (Python)
- **AI Orchestration**: LangChain
- **LLM**: Google Gemini (Gemini Flash)
- **Embeddings**: Google Generative AI Embeddings
- **Vector Database**: FAISS
- **Package Management**: `uv`

### Frontend
- **Framework**: React (Vite)
- **Styling**: Vanilla CSS
- **API Client**: Axios

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- Node.js & npm
- Google Gemini API Key

### Backend Setup
1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```
2. Create a `.env` file and add your API key:
   ```env
   GOOGLE_API_KEY=your_gemini_api_key_here
   ```
3. Install dependencies and run the server (using `uv`):
   ```bash
   uv run python main.py
   ```
   The backend will start at `http://localhost:5000`.

### Frontend Setup
1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
   The frontend will start at `http://localhost:5173`.

## 📖 Usage
1. Paste a YouTube video URL into the top input field.
2. Click **🚀 Process** to let the AI analyze the video.
3. Once processed, type your question in the second input field.
4. Click **💡 Ask AI** to get your answer!

## 📄 License
MIT
