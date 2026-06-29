##AI YouTube Tutor - Backend
Overview

The AI YouTube Tutor backend is a Flask-based REST API that powers the application's Retrieval-Augmented Generation (RAG) pipeline. It retrieves YouTube video transcripts, processes them into vector embeddings using Google's Gemini embedding model, stores them in a FAISS vector database, and answers user questions using Google's Gemini large language model.

##The backend exposes REST APIs that can be consumed by a React frontend or any other client application.

##Features
Fetch YouTube video transcripts
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