"""Vector retrieval over the retrieved web pages (Chroma, in-memory, one collection per run).

Why: search snippets are short and often miss the fact we need (e.g. the actual school names
live deep in a Wikipedia page). We chunk the FULL page text, embed it, and retrieve the most
relevant chunks for each field separately — so the model sees targeted evidence, not the first
400 characters of every page."""
import uuid
import chromadb
from .schemas import Source, Chunk

FIELD_QUERIES = {
    "current_role": "{name} current position and title at {company}",
    "education": "{name} education university degree graduated",
    "prior_roles": "{name} career history previous positions before",
    "board_seats": "{name} board of directors member serves on board",
    "notable_facts": "{name} joined company year milestones achievements",
}


def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    step = size - overlap
    return [text[i:i + size] for i in range(0, max(len(text) - overlap, 1), step)]


class SourceIndex:
    def __init__(self, embedding_function=None):
        self._client = chromadb.EphemeralClient()
        kwargs = {"embedding_function": embedding_function} if embedding_function else {}
        self._name = "src_" + uuid.uuid4().hex[:10]
        self._col = self._client.create_collection(self._name, **kwargs)
        self.n_chunks = 0

    def add(self, sources: list[Source]) -> None:
        ids, docs, metas = [], [], []
        for s in sources:
            for j, c in enumerate(chunk_text(s.raw or s.snippet)):
                ids.append(f"{self.n_chunks}")
                docs.append(c)
                metas.append({"url": s.url, "title": s.title, "j": j})
                self.n_chunks += 1
        if ids:
            self._col.add(ids=ids, documents=docs, metadatas=metas)

    def query(self, question: str, k: int = 4) -> list[Chunk]:
        if self.n_chunks == 0:
            return []
        r = self._col.query(query_texts=[question], n_results=min(k, self.n_chunks))
        return [Chunk(url=m["url"], text=d) for d, m in zip(r["documents"][0], r["metadatas"][0])]

    def close(self) -> None:
        try:
            self._client.delete_collection(self._name)
        except Exception:
            pass


def retrieve_for_fields(index: SourceIndex, name: str, company: str, k: int = 4) -> list[Chunk]:
    """Per-field retrieval, de-duplicated, preserving field order."""
    seen, out = set(), []
    for q in FIELD_QUERIES.values():
        for c in index.query(q.format(name=name, company=company), k=k):
            key = (c.url, c.text[:80])
            if key not in seen:
                seen.add(key)
                out.append(c)
    return out
