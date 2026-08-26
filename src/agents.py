import os
import time
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_groq import ChatGroq
from langchain_chroma import Chroma
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from .structure_outputs import *
from .prompts import *


def with_retry(chain, max_retries=5):
    """Wrap a chain with automatic retry on 429 rate limit errors."""
    def invoke_with_retry(inputs):
        for attempt in range(max_retries):
            try:
                return chain.invoke(inputs)
            except Exception as e:
                err = str(e)
                if '429' in err or 'RESOURCE_EXHAUSTED' in err:
                    # Parse suggested retry delay from error or use exponential backoff
                    wait = 60 * (attempt + 1)
                    import re
                    match = re.search(r'retry in (\d+)', err)
                    if match:
                        wait = int(match.group(1)) + 2
                    print(f"[Rate limit hit] Waiting {wait}s before retry {attempt+1}/{max_retries}...")
                    time.sleep(wait)
                else:
                    raise
        return chain.invoke(inputs)
    return RunnableLambda(invoke_with_retry)

class Agents():
    def __init__(self):
        # Choose which LLMs to use for each agent (Groq or Gemini)
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key and groq_key != "your_groq_api_key_here":
            llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.1)
        else:
            llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)
        
        # QA assistant chat
        embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", output_dimensionality=768)
        vectorstore = Chroma(persist_directory="db", embedding_function=embeddings)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
        self.vectorstore = vectorstore
        self.retriever = retriever

        # Categorize email chain
        email_category_prompt = PromptTemplate(
            template=CATEGORIZE_EMAIL_PROMPT, 
            input_variables=["email"]
        )
        self.categorize_email = with_retry(
            email_category_prompt | 
            llm.with_structured_output(CategorizeEmailOutput)
        )

        # Used to design queries for RAG retrieval
        generate_query_prompt = PromptTemplate(
            template=GENERATE_RAG_QUERIES_PROMPT, 
            input_variables=["email"]
        )
        self.design_rag_queries = with_retry(
            generate_query_prompt | 
            llm.with_structured_output(RAGQueriesOutput)
        )
        
        # Generate answer to queries using RAG
        qa_prompt = ChatPromptTemplate.from_template(GENERATE_RAG_ANSWER_PROMPT)
        self.generate_rag_answer = (
            {"context": retriever, "question": RunnablePassthrough()}
            | qa_prompt
            | llm
            | StrOutputParser()
        )

        # Used to write a draft email based on category and related informations
        writer_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EMAIL_WRITER_PROMPT),
                MessagesPlaceholder("history"),
                ("human", "{email_information}")
            ]
        )
        self.email_writer = with_retry(
            writer_prompt | 
            llm.with_structured_output(WriterOutput)
        )

        # Verify the generated email
        proofreader_prompt = PromptTemplate(
            template=EMAIL_PROOFREADER_PROMPT, 
            input_variables=["initial_email", "generated_email"]
        )
        self.email_proofreader = with_retry(
            proofreader_prompt | 
            llm.with_structured_output(ProofReaderOutput) 
        )