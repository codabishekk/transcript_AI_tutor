import os

from dotenv import load_dotenv
load_dotenv()


from langchain_google_genai import (
    GoogleGenerativeAIEmbeddings,
    ChatGoogleGenerativeAI
)

from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain.chains import RetrievalQA

os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

qa_chain = None


def process_video(url, transcript):

    global qa_chain

    with open("transcript.txt", "w", encoding="utf-8") as f:
        f.write(transcript)

    loader = TextLoader("transcript.txt")

    docs = loader.load()

    splitter = CharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    documents = splitter.split_documents(docs)

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001"
    )

    vector_store = FAISS.from_documents(
        documents,
        embeddings
    )

    retriever = vector_store.as_retriever()

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash"
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