"""LangGraph pipeline (v2):

START → search → retrieve → extract → verify ─┬─ ok      → summarize → END
            ▲                                 ├─ retry   → search  (bounded)
            └─────────────────────────────────┘
                                              └─ abstain → abstain → summarize → END

- search     Tavily search; low-quality domains filtered out; results merged across retries
- retrieve   mode="rag": chunk full pages into Chroma, retrieve per field
             mode="baseline": first 400 chars of each search snippet (the v1 behaviour)
- extract    Gemini structured output → ExtractedFields; identity fields locked to input
- verify     deterministic: every cited URL must be one we actually retrieved
- abstain    blank any field whose citations don't check out, and say why
- summarize  LLM writes the summary from VERIFIED fields only; a deterministic check rejects
             any number/year not present in those fields; fallback = template summary
"""
import json
import re
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from . import tools
from .schemas import Source, Chunk, ExtractedFields, ExecutiveProfile, Verdict, FIELDS
from .prompts import EXTRACT_SYSTEM, EXTRACT_USER, SUMMARY_SYSTEM
from .rag import SourceIndex, retrieve_for_fields

MAX_ATTEMPTS = 2


class State(TypedDict, total=False):
    name: str
    title: str
    company: str
    mode: str                 # "rag" | "baseline"
    query: str
    sources: list[Source]
    evidence: list[Chunk]
    profile: ExecutiveProfile
    verdict: Verdict
    attempts: int
    llm_calls: int
    embedding_function: object  # optional override (tests)


# ---------------- nodes ----------------
def search(state: State) -> State:
    q = state.get("query") or f'"{state["name"]}" {state["title"]} {state["company"]}'
    new = tools.web_search(q, raw=state.get("mode", "rag") == "rag")
    merged = {s.url: s for s in state.get("sources", [])}
    for s in new:
        merged.setdefault(s.url, s)
    return {"sources": list(merged.values()), "query": q, "attempts": state.get("attempts", 0) + 1}


def retrieve(state: State) -> State:
    if state.get("mode", "rag") == "baseline":
        return {"evidence": [Chunk(url=s.url, text=f"{s.title} — {s.snippet[:400]}") for s in state["sources"]]}
    index = SourceIndex(state.get("embedding_function"))
    try:
        index.add(state["sources"])
        return {"evidence": retrieve_for_fields(index, state["name"], state["company"])}
    finally:
        index.close()


def extract(state: State) -> State:
    ev = "\n".join(f"{c.url} | {c.text}" for c in state["evidence"])
    model = tools.llm().with_structured_output(ExtractedFields)
    fields = model.invoke([("system", EXTRACT_SYSTEM),
                           ("user", EXTRACT_USER.format(name=state["name"], title=state["title"],
                                                        company=state["company"], evidence=ev))])
    profile = ExecutiveProfile(name=state["name"], title=state["title"], company=state["company"],
                               **fields.model_dump())            # identity locked to the input
    for f in FIELDS:                                             # note is only for blanks
        fld = getattr(profile, f)
        if fld.value is not None:
            fld.note = ""
    return {"profile": profile, "llm_calls": state.get("llm_calls", 0) + 1}


def verify(state: State) -> State:
    """No LLM here on purpose: a model can't be trusted to grade its own citations."""
    allowed = {s.url for s in state["sources"]}
    p = state["profile"]
    reasons = []
    for f in FIELDS:
        fld = getattr(p, f)
        if fld.value is not None and not fld.source_urls:
            reasons.append(f"{f}: value without citation")
        bad = [u for u in fld.source_urls if u not in allowed]
        if bad:
            reasons.append(f"{f}: cites URL not in retrieved sources {bad}")
    if not reasons:
        return {"verdict": Verdict(status="ok")}
    if state.get("attempts", 0) < MAX_ATTEMPTS:
        return {"verdict": Verdict(status="retry", reasons=reasons),
                "query": f'{state["name"]} {state["company"]} executive biography'}
    return {"verdict": Verdict(status="abstain", reasons=reasons)}


def abstain(state: State) -> State:
    """Blank every field whose citations don't check out — never fabricate."""
    p = state["profile"]
    allowed = {s.url for s in state["sources"]}
    for f in FIELDS:
        fld = getattr(p, f)
        fld.source_urls = [u for u in fld.source_urls if u in allowed]
        if fld.value is not None and not fld.source_urls:
            fld.value, fld.note = None, "unverifiable: no retrieved source supports this field"
    return {"profile": p}


_NUM = re.compile(r"\d+")


def ungrounded_numbers(summary: str, facts: str) -> list[str]:
    """Numbers/years in the summary that do not appear in the verified facts."""
    have = set(_NUM.findall(facts))
    return [n for n in _NUM.findall(summary) if n not in have]


def template_summary(p: ExecutiveProfile) -> str:
    parts = [f"{p.name} is {p.title} at {p.company}."]
    for label, f in [("Current role", "current_role"), ("Education", "education"),
                     ("Prior roles", "prior_roles"), ("Board seats", "board_seats"),
                     ("Notable", "notable_facts")]:
        v = getattr(p, f).value
        if v:
            parts.append(f"{label}: {v}.")
    return " ".join(parts)


def summarize(state: State) -> State:
    p = state["profile"]
    facts = {f: getattr(p, f).value for f in FIELDS}
    facts_json = json.dumps({"name": p.name, "title": p.title, "company": p.company, **facts})
    calls = state.get("llm_calls", 0)
    for _ in range(2):  # one retry with the same strict instruction
        text = tools.text_of(tools.llm().invoke([("system", SUMMARY_SYSTEM), ("user", facts_json)])).strip()
        calls += 1
        if text and not ungrounded_numbers(text, facts_json):
            p.summary, p.summary_grounded = text, True
            return {"profile": p, "llm_calls": calls}
    p.summary, p.summary_grounded = template_summary(p), True  # deterministic fallback, grounded by construction
    p.meta["summary_fallback"] = True
    return {"profile": p, "llm_calls": calls}


def route(state: State) -> str:
    return {"ok": "summarize", "retry": "search", "abstain": "abstain"}[state["verdict"].status]


# ---------------- graph ----------------
def build_graph():
    g = StateGraph(State)
    for n, fn in [("search", search), ("retrieve", retrieve), ("extract", extract),
                  ("verify", verify), ("abstain", abstain), ("summarize", summarize)]:
        g.add_node(n, fn)
    g.add_edge(START, "search")
    g.add_edge("search", "retrieve")
    g.add_edge("retrieve", "extract")
    g.add_edge("extract", "verify")
    g.add_conditional_edges("verify", route, {"summarize": "summarize", "search": "search", "abstain": "abstain"})
    g.add_edge("abstain", "summarize")
    g.add_edge("summarize", END)
    return g.compile()


def run(name: str, title: str, company: str, mode: str = "rag", embedding_function=None) -> ExecutiveProfile:
    t0 = time.time()
    init = {"name": name, "title": title, "company": company, "mode": mode, "attempts": 0, "llm_calls": 0}
    if embedding_function is not None:
        init["embedding_function"] = embedding_function
    out = build_graph().invoke(init)
    p = out["profile"]
    p.meta.update({"mode": mode, "attempts": out["attempts"], "llm_calls": out["llm_calls"],
                   "n_sources": len(out["sources"]), "n_evidence_chunks": len(out["evidence"]),
                   "verdict": out["verdict"].status, "latency_s": round(time.time() - t0, 2)})
    return p
