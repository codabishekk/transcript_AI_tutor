import os

from dotenv import load_dotenv
load_dotenv()

from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi

from langchain_google_genai import (
    GoogleGenerativeAIEmbeddings,
    ChatGoogleGenerativeAI
)

from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain.chains import RetrievalQA

google_api_key = os.getenv("GOOGLE_API_KEY")
if google_api_key:
    os.environ["GOOGLE_API_KEY"] = google_api_key


qa_chain = None


def get_transcript(url):
    try:
        video_id = YouTube(url).video_id
    except Exception:
        raise ValueError("Invalid YouTube URL. Please check the link.")

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        # Try to find English first, fallback to any available language
        try:
            transcript_obj = transcript_list.find_transcript(['en'])
        except Exception:
            # If English is not found, take the first available transcript
            try:
                transcript_obj = next(iter(transcript_list))
            except StopIteration:
                raise ValueError("No transcripts are available for this video.")
        
        transcript = transcript_obj.fetch()
    except Exception as e:
        if "No transcripts are available" in str(e):
             raise ValueError(str(e))
        raise ValueError(f"Could not fetch transcript: {str(e)}")

    text = " ".join([item.text for item in transcript])

    if not text.strip():
        raise ValueError("The video has an empty transcript.")

    return text


def process_video(url):

    global qa_chain

    transcript = get_transcript(url)

    from langchain_core.documents import Document
    docs = [Document(page_content=transcript)]

    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )

    documents = splitter.split_documents(docs)
    
    if not documents:
        raise ValueError("Could not split transcript into any documents.")

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001"
    )

    vector_store = FAISS.from_documents(
        documents,
        embeddings
    )

    retriever = vector_store.as_retriever()

    llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview"
    )

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff"
    )


def ask_question(question):

    global qa_chain

    if qa_chain is None:
        return "Please process a YouTube video first."

    return qa_chain.run(question)