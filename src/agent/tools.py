"""External tools: web search + Gemini client."""
import os
from dotenv import load_dotenv
from tavily import TavilyClient
from langchain_google_genai import ChatGoogleGenerativeAI
from .schemas import Source

load_dotenv()


def web_search(query: str, k: int = 6) -> list[Source]:
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    res = client.search(query, max_results=k, search_depth="advanced")
    return [Source(url=r["url"], title=r.get("title", ""), snippet=r.get("content", ""))
            for r in res.get("results", [])]


def llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    primary = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
                                     temperature=temperature, max_retries=5, timeout=90)
    return primary
