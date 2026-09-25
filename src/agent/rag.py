"""Phase 2: vector store over retrieved sources (Chroma). Wire into graph.py after Phase 1 works.

Why: with many sources per executive, dump them ALL into a vector store and retrieve only the
chunks relevant to each field (education, board seats, ...) instead of stuffing every snippet
into one prompt. That is what turns "search-augmented" into a proper RAG pipeline."""
import chromadb
from chromadb.utils import embedding_functions
from .schemas import Source

_client = chromadb.PersistentClient(path="chroma_db")
_embed = embedding_functions.DefaultEmbeddingFunction()  # local, no API key needed


def index_sources(person_key: str, sources: list[Source]) -> None:
    col = _client.get_or_create_collection(name="sources", embedding_function=_embed)
    col.upsert(ids=[f"{person_key}:{i}" for i in range(len(sources))],
               documents=[f"{s.title}\n{s.snippet}" for s in sources],
               metadatas=[{"url": s.url, "person": person_key} for s in sources])


def retrieve(person_key: str, question: str, k: int = 4) -> list[Source]:
    col = _client.get_or_create_collection(name="sources", embedding_function=_embed)
    r = col.query(query_texts=[question], n_results=k, where={"person": person_key})
    return [Source(url=m["url"], snippet=d) for d, m in zip(r["documents"][0], r["metadatas"][0])]
