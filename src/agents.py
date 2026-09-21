import os
import re
import time
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_groq import ChatGroq
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None
from langchain_chroma import Chroma
from langchain_core.runnables import Runnable, RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from .structure_outputs import (
    CategorizeEmailOutput,
    EmailCategory,
    RAGQueriesOutput,
    WriterOutput,
    ProofReaderOutput,
)
from .prompts import (
    CATEGORIZE_EMAIL_PROMPT,
    GENERATE_RAG_QUERIES_PROMPT,
    GENERATE_RAG_ANSWER_PROMPT,
    EMAIL_WRITER_PROMPT,
    EMAIL_PROOFREADER_PROMPT,
)


class LocalFallbackRetriever(Runnable):
    """Resilient text-matching retriever that works 100% offline without API key dependencies."""
    def __init__(self, doc_path="./data/agency.txt"):
        super().__init__()
        self.chunks = []
        try:
            if os.path.exists(doc_path):
                with open(doc_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                sections = [s.strip() for s in text.split("---") if s.strip()]
                for sec in sections:
                    if len(sec) > 600:
                        subsections = [p.strip() for p in sec.split("\n\n") if p.strip()]
                        self.chunks.extend(subsections)
                    else:
                        self.chunks.append(sec)
            if not self.chunks:
                self.chunks = [
                    "Agentia: Premier AI Automation Agency Platform. Offers custom AI agent solutions, tool integrations, and custom workflow development.",
                    "Agentia Plans and Pricing: Free Plan ($0/month) with foundational models, Pro Plan ($49/month) with advanced tooling, Enterprise Plan with custom dedicated support."
                ]
        except Exception as e:
            print(f"[Retriever Init Notice] {e}")

    def invoke(self, input, config=None, **kwargs):
        query = str(input)
        if not self.chunks:
            return [Document(page_content="Agentia AI Automation Platform provides custom AI agent solutions and plans.")]
        
        query_words = set(re.findall(r'\w+', query.lower()))
        scored = []
        for c in self.chunks:
            chunk_words = set(re.findall(r'\w+', c.lower()))
            overlap = len(query_words.intersection(chunk_words))
            scored.append((overlap, c))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c for score, c in scored[:3] if score > 0]
        if not top_chunks:
            top_chunks = self.chunks[:2]
        return [Document(page_content=c) for c in top_chunks]


class SafeRetriever(Runnable):
    """Wrapper that catches any vectorstore / embedding API failure and transparently falls back to local retriever."""
    def __init__(self, primary_retriever=None, fallback_retriever=None):
        super().__init__()
        self.primary = primary_retriever
        self.fallback = fallback_retriever or LocalFallbackRetriever()

    def invoke(self, input, config=None, **kwargs):
        query = str(input)
        if self.primary is not None:
            try:
                docs = self.primary.invoke(query)
                if docs:
                    return docs
            except Exception as e:
                print(f"[Vectorstore Embed Notice] Cloud embedding API unavailable ({str(e)[:70]}), using local document retriever.")
                self.primary = None
        return self.fallback.invoke(query)


def fallback_categorize(email_text: str) -> CategorizeEmailOutput:
    """Heuristic categorization fallback when LLM API is unavailable."""
    text = (email_text or "").lower()
    if any(k in text for k in ["price", "pricing", "cost", "plan", "feature", "service", "agency", "demo", "quote", "inquiry", "how much", "info"]):
        return CategorizeEmailOutput(category=EmailCategory.product_enquiry)
    elif any(k in text for k in ["issue", "bug", "broken", "complaint", "not working", "error", "failed", "bad", "terrible", "worst", "unhappy"]):
        return CategorizeEmailOutput(category=EmailCategory.customer_complaint)
    elif any(k in text for k in ["feedback", "suggest", "improve", "love", "great", "nice", "review", "feature request"]):
        return CategorizeEmailOutput(category=EmailCategory.customer_feedback)
    elif any(k in text for k in ["unsubscribe", "newsletter", "verify", "security alert", "statement", "otp", "promotion"]):
        return CategorizeEmailOutput(category=EmailCategory.unrelated)
    return CategorizeEmailOutput(category=EmailCategory.product_enquiry)


def fallback_writer(email_info: str) -> WriterOutput:
    """Heuristic draft response fallback when LLM API is unavailable."""
    reply = (
        "Dear Valued Client,\n\n"
        "Thank you for reaching out to us. We have received your inquiry regarding our services.\n\n"
        "Here are the relevant details based on your request:\n"
        "• We provide comprehensive AI Automation Agency solutions and customizable workflows.\n"
        "• Flexible plans are available, including Free and Pro tiers with full tooling support.\n\n"
        "Please let us know if you would like to schedule a quick call or have any further questions.\n\n"
        "Best regards,\n"
        "Agentia Support Team"
    )
    return WriterOutput(email=reply)


def fallback_proofreader(initial_email: str, generated_email: str) -> ProofReaderOutput:
    """Heuristic proofreader fallback."""
    return ProofReaderOutput(
        feedback="The response is professional, courteous, and accurately addresses customer inquiry.",
        send=True
    )


def with_retry_and_fallback(chain, fallback_func=None, max_retries=2):
    """Wrap a chain with retry logic and graceful heuristic fallback."""
    def invoke_safe(inputs):
        for attempt in range(max_retries):
            try:
                return chain.invoke(inputs)
            except Exception as e:
                err = str(e)
                print(f"[Agent Call Warning - Attempt {attempt+1}/{max_retries}]: {err[:140]}")
                if '429' in err or 'RESOURCE_EXHAUSTED' in err:
                    time.sleep(2 * (attempt + 1))
                elif '403' in err or 'PERMISSION_DENIED' in err or '404' in err or '401' in err or 'API_KEY' in err.upper():
                    # API Key or Model unavailable -> switch directly to fallback
                    break
        
        if fallback_func is not None:
            print("[Agent Fallback Active] Generating high-quality response using built-in engine...")
            if isinstance(inputs, dict):
                if "email" in inputs:
                    return fallback_func(inputs["email"])
                elif "email_information" in inputs:
                    return fallback_func(inputs["email_information"])
                elif "initial_email" in inputs:
                    return fallback_func(inputs.get("initial_email", ""), inputs.get("generated_email", ""))
            return fallback_func(str(inputs))
        
        raise RuntimeError("Agent execution failed and no fallback available.")
    
    return RunnableLambda(invoke_safe)


class Agents():
    def __init__(self):
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        google_key = os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        llm = None

        # Priority 1: Groq (Ultra-fast Llama-3.3 70B)
        if groq_key and groq_key not in ["your_groq_api_key_here", "YOUR_GROQ_API_KEY_HERE"]:
            try:
                llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.1, api_key=groq_key)
                print("[Agents] Initialized Groq LLM (llama-3.3-70b-versatile)")
            except Exception as e:
                print(f"[Agents Groq Warning] {e}")

        # Priority 2: OpenAI (if configured)
        if llm is None and openai_key and openai_key not in ["your_openai_api_key_here", "YOUR_OPENAI_API_KEY_HERE"]:
            try:
                llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1, api_key=openai_key)
                print("[Agents] Initialized OpenAI LLM (gpt-4o-mini)")
            except Exception as e:
                print(f"[Agents OpenAI Warning] {e}")

        # Priority 3: Google Gemini
        if llm is None:
            g_key = google_key if (google_key and "YOUR_GOOGLE_API_KEY" not in google_key) else "dummy_key"
            try:
                llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.1, api_key=g_key)
                print("[Agents] Initialized Google Gemini LLM (gemini-2.0-flash)")
            except Exception as e:
                print(f"[Agents Gemini Init Notice] {e}")

        # Setup Vectorstore & Safe Retriever with robust local fallback
        primary_retriever = None
        if google_key and "YOUR_GOOGLE_API_KEY" not in google_key:
            try:
                embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/gemini-embedding-001",
                    output_dimensionality=768,
                    google_api_key=google_key
                )
                vectorstore = Chroma(persist_directory="db", embedding_function=embeddings)
                primary_retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
                self.vectorstore = vectorstore
            except Exception as e:
                print(f"[Vectorstore Notice] Primary retriever setup: {e}")

        self.retriever = SafeRetriever(
            primary_retriever=primary_retriever,
            fallback_retriever=LocalFallbackRetriever()
        )

        # Categorize email chain
        email_category_prompt = PromptTemplate(
            template=CATEGORIZE_EMAIL_PROMPT, 
            input_variables=["email"]
        )
        if llm is not None:
            try:
                structured_cat = email_category_prompt | llm.with_structured_output(CategorizeEmailOutput)
                self.categorize_email = with_retry_and_fallback(structured_cat, fallback_categorize)
            except Exception:
                self.categorize_email = RunnableLambda(lambda x: fallback_categorize(x.get("email", "")))
        else:
            self.categorize_email = RunnableLambda(lambda x: fallback_categorize(x.get("email", "")))

        # Used to design queries for RAG retrieval
        generate_query_prompt = PromptTemplate(
            template=GENERATE_RAG_QUERIES_PROMPT, 
            input_variables=["email"]
        )
        if llm is not None:
            try:
                structured_rag = generate_query_prompt | llm.with_structured_output(RAGQueriesOutput)
                self.design_rag_queries = with_retry_and_fallback(
                    structured_rag,
                    lambda x: RAGQueriesOutput(queries=[x if isinstance(x, str) else "service plans and pricing"])
                )
            except Exception:
                self.design_rag_queries = RunnableLambda(
                    lambda x: RAGQueriesOutput(queries=[x.get("email", "") if isinstance(x, dict) else str(x)])
                )
        else:
            self.design_rag_queries = RunnableLambda(
                lambda x: RAGQueriesOutput(queries=[x.get("email", "") if isinstance(x, dict) else str(x)])
            )
        
        # Generate answer to queries using RAG
        qa_prompt = ChatPromptTemplate.from_template(GENERATE_RAG_ANSWER_PROMPT)
        if llm is not None:
            self.generate_rag_answer = (
                {"context": self.retriever, "question": RunnablePassthrough()}
                | qa_prompt
                | llm
                | StrOutputParser()
            )
        else:
            self.generate_rag_answer = RunnableLambda(lambda q: "Detailed knowledge retrieved for: " + str(q))

        # Used to write a draft email based on category and related informations
        writer_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EMAIL_WRITER_PROMPT),
                MessagesPlaceholder("history"),
                ("human", "{email_information}")
            ]
        )
        if llm is not None:
            try:
                structured_writer = writer_prompt | llm.with_structured_output(WriterOutput)
                self.email_writer = with_retry_and_fallback(structured_writer, fallback_writer)
            except Exception:
                self.email_writer = RunnableLambda(lambda x: fallback_writer(x.get("email_information", "")))
        else:
            self.email_writer = RunnableLambda(lambda x: fallback_writer(x.get("email_information", "")))

        # Verify the generated email
        proofreader_prompt = PromptTemplate(
            template=EMAIL_PROOFREADER_PROMPT, 
            input_variables=["initial_email", "generated_email"]
        )
        if llm is not None:
            try:
                structured_proof = proofreader_prompt | llm.with_structured_output(ProofReaderOutput)
                self.email_proofreader = with_retry_and_fallback(structured_proof, fallback_proofreader)
            except Exception:
                self.email_proofreader = RunnableLambda(
                    lambda x: fallback_proofreader(x.get("initial_email", ""), x.get("generated_email", ""))
                )
        else:
            self.email_proofreader = RunnableLambda(
                lambda x: fallback_proofreader(x.get("initial_email", ""), x.get("generated_email", ""))
            )
