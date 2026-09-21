import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

RAG_SEARCH_PROMPT_TEMPLATE = """
Using the following pieces of retrieved context, answer the question comprehensively and concisely.
Ensure your response fully addresses the question based on the given context.

**IMPORTANT:**
Just provide the answer and never mention or refer to having access to the external context or information in your answer.
If you are unable to determine the answer from the provided context, state 'I don't know.'

Question: {question}
Context: {context}
"""

print("Loading & Chunking Docs...")
doc_path = "./data/agency.txt"
if not os.path.exists(doc_path):
    print(f"Error: {doc_path} not found.")
    exit(1)

loader = TextLoader(doc_path, encoding="utf-8")
docs = loader.load()

doc_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
doc_chunks = doc_splitter.split_documents(docs)
print(f"Created {len(doc_chunks)} chunks.")

google_key = os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
groq_key = os.getenv("GROQ_API_KEY", "").strip()
openai_key = os.getenv("OPENAI_API_KEY", "").strip()

try:
    print("Creating vector embeddings...")
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        output_dimensionality=768,
        google_api_key=google_key
    )
    vectorstore = Chroma.from_documents(doc_chunks, embeddings, persist_directory="db")
    vectorstore_retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    print("Vectorstore initialized successfully in db/ directory.")
except Exception as e:
    print(f"[Vectorstore Notice] Cloud embedding unavailable: {e}")
    from src.agents import LocalFallbackRetriever
    vectorstore_retriever = LocalFallbackRetriever(doc_path=doc_path)

# LLM Selection
llm = None
if groq_key and "your_groq_api_key" not in groq_key:
    try:
        llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.1, api_key=groq_key)
    except Exception:
        pass
if llm is None and openai_key and "your_openai_api_key" not in openai_key:
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1, api_key=openai_key)
    except Exception:
        pass
if llm is None and google_key and "YOUR_GOOGLE_API_KEY" not in google_key:
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1, api_key=google_key)
    except Exception:
        pass

print("\nTesting RAG chain...")
query = "What are your pricing options?"
if llm is not None:
    try:
        prompt = ChatPromptTemplate.from_template(RAG_SEARCH_PROMPT_TEMPLATE)
        rag_chain = (
            {"context": vectorstore_retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        result = rag_chain.invoke(query)
        print(f"Question: {query}")
        print(f"Answer: {result}")
    except Exception as e:
        print(f"LLM Call Notice ({e}). Retrieved context:")
        docs = vectorstore_retriever.invoke(query)
        for i, d in enumerate(docs):
            print(f"[{i+1}] {d.page_content[:150]}...")
else:
    print(f"Retrieved context for '{query}':")
    docs = vectorstore_retriever.invoke(query)
    for i, d in enumerate(docs):
        print(f"[{i+1}] {d.page_content[:150]}...")
