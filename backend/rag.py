import os
import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module="langchain_google_genai.*")
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai.*")

from dotenv import load_dotenv
load_dotenv()

import youtube_transcript_api


from langchain_google_genai import (
    GoogleGenerativeAIEmbeddings,
    ChatGoogleGenerativeAI
)

from langchain_community.vectorstores import FAISS
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.retrieval import create_retrieval_chain
from langchain_core.prompts import ChatPromptTemplate


google_api_key = os.getenv("GOOGLE_API_KEY")
if google_api_key:
    os.environ["GOOGLE_API_KEY"] = google_api_key


qa_chain = None


def get_transcript(url):
    import re
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not match:
        raise ValueError("Invalid YouTube URL. Please check the link.")
    video_id = match.group(1)

    cookies = None
    cookie_path = os.path.join(os.path.dirname(__file__), 'cookies.txt')
    if os.path.exists(cookie_path):
        cookies = cookie_path

    proxy = os.getenv("YOUTUBE_PROXY")
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy

    try:
        transcript = youtube_transcript_api.YouTubeTranscriptApi.get_transcript(
            video_id, languages=['en'], cookies=cookies
        )
    except Exception as e:
        error_msg = str(e)
        raise ValueError(f"Transcript Error: {error_msg}")

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



    prompt = ChatPromptTemplate.from_template(
        "Use the following context to answer the question. "
        "If you don't know, say so.\n\nContext: {context}\n\nQuestion: {input}"
    )
    combine_docs_chain = create_stuff_documents_chain(llm, prompt)
    qa_chain = create_retrieval_chain(retriever, combine_docs_chain)


def ask_question(question):

    global qa_chain

    if qa_chain is None:
        return "Please process a YouTube video first."

    result = qa_chain.invoke({"input": question})
    return result["answer"]