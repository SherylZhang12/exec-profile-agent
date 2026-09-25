"""External tools: web search (with source-quality filter) + Gemini client."""
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from .schemas import Source

load_dotenv()

# User-generated / social sites: not acceptable as evidence for a factual profile.
LOW_QUALITY_DOMAINS = {
    "scribd.com", "pinterest.com", "quora.com", "reddit.com", "facebook.com",
    "instagram.com", "tiktok.com", "x.com", "twitter.com", "medium.com", "slideshare.net","fandom.com", "clay.com", "zoominfo.com", "rocketreach.co", "signalhire.com",
"contactout.com", "theorg.com", "apollo.io",
}


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_low_quality(url: str) -> bool:
    d = domain(url)
    return any(d == bad or d.endswith("." + bad) for bad in LOW_QUALITY_DOMAINS)


def web_search(query: str, k: int = 8, raw: bool = False) -> list[Source]:
    from tavily import TavilyClient  # imported lazily so tests don't need the package configured
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    res = client.search(query, max_results=k, search_depth="advanced", include_raw_content=raw)
    return [Source(url=r["url"], title=r.get("title") or "", snippet=r.get("content") or "",
                   raw=r.get("raw_content") or "")
            for r in res.get("results", []) if not is_low_quality(r["url"])]


def llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    # max_retries: exponential backoff on transient errors (e.g. 503 "high demand")
    return ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
                                  temperature=temperature, max_retries=5, timeout=90)


def text_of(msg) -> str:
    """AIMessage.content can be a string or a list of parts depending on the model."""
    c = msg.content
    if isinstance(c, str):
        return c
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
