from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from langchain_core.tools import tool
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_chroma import Chroma
from langchain_core.documents import Document
from datetime import datetime, timezone
from typing import List
from ddgs import DDGS
from typing import Any, Dict, List
from crawl4ai import AsyncWebCrawler
from dataclasses import dataclass
import asyncio

# --- LOCAL DB SETUP ---
DB_PATH = "./research_db"
embeddings_model = OllamaEmbeddings(
    model="bge-m3", 
    base_url="http://jcs-macbook-pro:11434"
)

# Initialize ChromaDB
vectorstore = Chroma(
    collection_name="research_chunks",
    embedding_function=embeddings_model,
    persist_directory=DB_PATH
)

@dataclass
class ProcessedChunk:
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]

# --- AI UTILITIES (SYNCHRONOUS) ---

def get_title_and_summary(chunk: str, url: str) -> Dict[str, str]:
    llm = ChatOllama(
        model="mistral:v0.3", 
        base_url="http://jcs-macbook-pro:11434",
        temperature=0,
        format="json"
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract 'title' and 'summary' from this chunk as JSON."),
        ("user", "URL: {url}\n\nContent:\n{content}")
    ])
    chain = prompt | llm | JsonOutputParser()
    try:
        return chain.invoke({"url": url, "content": chunk[:1000]})
    except Exception as e:
        print(f"LLM Error: {e}")
        return {"title": "Untitled Chunk", "summary": "No summary available"}

# --- SEMAPHORE HELPER ---
# Do not initialize it here globally
_ollama_semaphore = None

def get_ollama_semaphore():
    """Lazily initializes the semaphore in the current active event loop."""
    global _ollama_semaphore
    if _ollama_semaphore is None:
        _ollama_semaphore = asyncio.Semaphore(2)
    return _ollama_semaphore

# --- PROCESSING LOGIC ---

def chunk_text(text: str, chunk_size: int = 5000) -> List[str]:
    # Basic splitting
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

async def process_chunk(chunk: str, chunk_number: int, url: str) -> ProcessedChunk:
    # Get the semaphore that is bound to the current loop being run by the tool
    semaphore = get_ollama_semaphore()
    
    async with semaphore:
        # Move blocking sync calls to threads
        extracted = await asyncio.to_thread(get_title_and_summary, chunk, url)

    metadata = {
        "url": url,
        "chunk_number": chunk_number,
        "title": extracted.get('title', 'Untitled'),
        "summary": extracted.get('summary', 'No summary'),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "source": "research_agent"
    }
    return ProcessedChunk(
        url=url,
        chunk_number=chunk_number,
        title=extracted.get('title', 'Untitled'),
        summary=extracted.get('summary', 'No summary'),
        content=chunk,
        metadata=metadata
    )

async def insert_chunks_local(chunks: List[ProcessedChunk]):
    """Insert processed chunks into the local ChromaDB."""
    try:
        documents = [
            Document(
                page_content=c.content,
                metadata=c.metadata
            ) for c in chunks
        ]
        # ChromaDB handles embeddings internally via the embeddings_model we passed
        await asyncio.to_thread(vectorstore.add_documents, documents)
        print(f"✓ Saved {len(chunks)} chunks to local DB from {chunks[0].url if chunks else 'N/A'}")
    except Exception as e:
        print(f"✗ Local DB Error: {e}")

async def process_and_store_document(url: str, markdown: str):
    chunks = chunk_text(markdown)
    tasks = [process_chunk(c, i, url) for i, c in enumerate(chunks)]
    processed_chunks = await asyncio.gather(*tasks)
    
    # Store all chunks for this document
    await insert_chunks_local(processed_chunks)

# --- CRAWLER ---

async def crawl_parallel(urls: List[str], max_concurrent: int = 3):
    print(f"\n=== Local Research: Crawling {len(urls)} URLs ===")
    browser_config = BrowserConfig(headless=True, extra_args=["--no-sandbox"])
    crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()

    try:
        for i in range(0, len(urls), max_concurrent):
            batch = urls[i : i + max_concurrent]
            print(f"Processing batch {i//max_concurrent + 1}...")
            
            tasks = [crawler.arun(url=url, config=crawl_config) for url in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for url, result in zip(batch, results):
                if not isinstance(result, Exception) and result.success:
                    await process_and_store_document(url, result.markdown)
                else:
                    print(f"Failed to crawl: {url}")
    finally:
        await crawler.close()


@tool(description="Pull Data in .md files from the internet for research.")
def crawl_data(query: str, max_results: int = 10):
    urls = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            urls.append(r["href"])

    print(f"Found {len(urls)} URLs. Starting local crawl...")
    import nest_asyncio
    nest_asyncio.apply()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(crawl_parallel(urls, max_concurrent=3))


@tool(description="""Retrieve relevant documentation chunks based on the query with RAG. Use this to find factual information from crawled sites. Result: formatted string with top 5 chunks.""")
def retrieve_relevant_documentation(query: str) -> str:
    # Logic remains the same, accessing your shared vectorstore
    try:
        # Chroma/LangChain search logic
        results = vectorstore.similarity_search(query, k=5)
        
        if not results:
            return "No relevant documentation chunks found in the local database."
            
        formatted_results = []
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("url", "Unknown Source")
            title = doc.metadata.get("title", "Untitled")
            
            formatted_results.append(
                f"--- Result {i} ---\n"
                f"Source: {source}\n"
                f"Title: {title}\n"
                f"Content: {doc.page_content}\n"
            )
            
        return "\n".join(formatted_results)
        
    except Exception as e:
        return f"Error retrieving documentation: {str(e)}"