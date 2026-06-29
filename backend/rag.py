import os

from dotenv import load_dotenv
load_dotenv()

from pytube import YouTube
import youtube_transcript_api


from langchain_google_genai import (
    GoogleGenerativeAIEmbeddings,
    ChatGoogleGenerativeAI
)

from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_classic.chains import RetrievalQA


google_api_key = os.getenv("GOOGLE_API_KEY")
if google_api_key:
    os.environ["GOOGLE_API_KEY"] = google_api_key


qa_chain = None


def get_transcript(url):
    import re
    # Extract video ID using regex (more reliable than pytube)
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not match:
        raise ValueError("Invalid YouTube URL. Please check the link.")
    video_id = match.group(1)


    try:
        # Use plurality of checks to find the right method
        api_class = getattr(youtube_transcript_api, 'YouTubeTranscriptApi', None)
        if api_class is None:
             raise ValueError(f"Could not find YouTubeTranscriptApi class in module. Available: {dir(youtube_transcript_api)}")
        
        # Determine the correct method name (sometimes it is list_transcripts, sometimes get_transcript)
        method_name = 'get_transcript' if hasattr(api_class, 'get_transcript') else 'list_transcripts'
        method = getattr(api_class, method_name)

        if method_name == 'get_transcript':
            try:
                transcript = method(video_id, languages=['en'])
            except Exception:
                transcript = method(video_id)
        else:
            # Fallback to list_transcripts logic if that's what's available
            transcript_list = method(video_id)
            try:
                transcript = transcript_list.find_transcript(['en']).fetch()
            except Exception:
                transcript = next(iter(transcript_list)).fetch()

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        available_methods = dir(getattr(youtube_transcript_api, 'YouTubeTranscriptApi', youtube_transcript_api))
        raise ValueError(f"Transcript Error: {str(e)}. Methods found: {available_methods}")




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
        model="models/gemini-embedding-001",
        google_api_key=google_api_key
    )


    vector_store = FAISS.from_documents(
        documents,
        embeddings
    )

    retriever = vector_store.as_retriever()

    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=google_api_key
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