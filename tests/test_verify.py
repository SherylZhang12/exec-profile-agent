"""Unit + end-to-end tests. No API keys or network needed: search/LLM/embeddings are stubbed."""
import hashlib
from src.agent import graph as g, tools
from src.agent.schemas import Source, ExecutiveProfile, ExtractedFields, Field_
from src.agent.rag import chunk_text


def _state(profile, urls):
    return {"sources": [Source(url=u) for u in urls], "profile": profile, "attempts": 5}


# ---- verify / abstain ----
def test_ok_when_every_value_is_cited():
    p = ExecutiveProfile(name="A", title="CEO", company="X",
                         current_role=Field_(value="CEO of X", source_urls=["https://x.com/a"]))
    assert g.verify(_state(p, ["https://x.com/a"]))["verdict"].status == "ok"


def test_uncited_value_is_caught():
    p = ExecutiveProfile(name="A", title="CEO", company="X", education=Field_(value="MIT"))
    v = g.verify(_state(p, ["https://x.com/a"]))["verdict"]
    assert v.status == "abstain" and "education" in v.reasons[0]


def test_hallucinated_url_is_caught_and_blanked():
    p = ExecutiveProfile(name="A", title="CEO", company="X",
                         education=Field_(value="MIT", source_urls=["https://made-up.com"]))
    s = _state(p, ["https://x.com/a"])
    assert g.verify(s)["verdict"].status == "abstain"
    out = g.abstain(s)["profile"]
    assert out.education.value is None and "unverifiable" in out.education.note


# ---- summary grounding ----
def test_ungrounded_numbers_detected():
    assert g.ungrounded_numbers("CEO since February 2014", '{"x": "joined in 1992"}') == ["2014"]
    assert g.ungrounded_numbers("Joined in 1992", '{"x": "joined in 1992"}') == []


# ---- source quality / chunking ----
def test_low_quality_domains_filtered():
    assert tools.is_low_quality("https://www.scribd.com/document/1")
    assert tools.is_low_quality("https://m.facebook.com/x")
    assert not tools.is_low_quality("https://news.microsoft.com/exec")


def test_chunking_covers_text_with_overlap():
    t = "word " * 1000
    cs = chunk_text(t, size=900, overlap=150)
    assert len(cs) > 1 and all(len(c) <= 900 for c in cs)
    assert cs[0][-150:] == cs[1][:150]


# ---- end-to-end with stubs ----
class HashEmbedding:
    """Deterministic toy embedding so Chroma runs offline in tests."""
    def __call__(self, input):
        return [[b / 255 for b in hashlib.sha256(t.encode()).digest()[:16]] for t in input]
    def name(self): return "hash-test"
    def is_legacy(self): return False
    def embed_query(self, input): return self(input)
    def get_config(self): return {}
    @staticmethod
    def build_from_config(config): return HashEmbedding()


class FakeLLM:
    def __init__(self, summary): self.summary = summary
    def with_structured_output(self, _): return self
    def invoke(self, msgs):
        if msgs[0][1].startswith("Write a neutral"):
            class M: content = self.summary
            return M()
        return ExtractedFields(
            current_role=Field_(value="CEO of Co", source_urls=["https://co.com/leadership"], note="restated"),
            education=Field_(value="Harvard", source_urls=["https://fake.example/bio"]))  # fabricated URL


def _run(monkeypatch, summary, mode):
    monkeypatch.setattr(tools, "web_search", lambda q, k=8, raw=False: [
        Source(url="https://co.com/leadership", title="Leadership",
               snippet="Jane Doe is CEO of Co.", raw="Jane Doe is the chief executive officer of Co. " * 40),
        Source(url="https://www.scribd.com/doc", title="junk")][:1])
    monkeypatch.setattr(tools, "llm", lambda temperature=0.0: FakeLLM(summary))
    return g.run("Jane Doe", "CEO", "Co", mode=mode, embedding_function=HashEmbedding())


def test_e2e_rag_blanks_fabrication_locks_identity_grounds_summary(monkeypatch):
    p = _run(monkeypatch, "Jane Doe is CEO of Co.", "rag")
    assert p.title == "CEO"                               # identity locked to input
    assert p.current_role.value == "CEO of Co" and p.current_role.note == ""  # note cleared
    assert p.education.value is None                      # fabricated citation removed
    assert p.summary_grounded and p.meta["verdict"] == "abstain" and p.meta["attempts"] == 2


def test_e2e_summary_with_invented_year_falls_back(monkeypatch):
    p = _run(monkeypatch, "Jane Doe became CEO in 2014.", "baseline")
    assert p.meta.get("summary_fallback") and "2014" not in p.summary
