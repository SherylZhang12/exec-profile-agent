"""LangGraph pipeline: search -> extract -> verify -> (retry | emit | abstain).

State flows through four nodes. `verify` is the reliability gate: it checks that every
non-null field cites a URL that actually appeared in the search results, and can send the
graph back to `search` with a refined query (bounded by MAX_ATTEMPTS)."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .schemas import Source, ExecutiveProfile, Verdict
from .tools import web_search, llm
from .prompts import EXTRACT_SYSTEM, EXTRACT_USER

MAX_ATTEMPTS = 2
FIELDS = ["current_role", "education", "prior_roles", "board_seats", "notable_facts"]


class State(TypedDict, total=False):
    name: str
    title: str
    company: str
    query: str
    sources: list[Source]
    profile: ExecutiveProfile | None
    verdict: Verdict | None
    attempts: int


# ---------- nodes ----------
def search(state: State) -> State:
    q = state.get("query") or f'"{state["name"]}" {state["title"]} {state["company"]}'
    return {"sources": web_search(q), "query": q, "attempts": state.get("attempts", 0) + 1}


def extract(state: State) -> State:
    src_text = "\n".join(f"{i} | {s.url} | {s.title} | {s.snippet[:400]}"
                         for i, s in enumerate(state["sources"]))
    model = llm().with_structured_output(ExecutiveProfile)
    profile = model.invoke([("system", EXTRACT_SYSTEM),
                            ("user", EXTRACT_USER.format(name=state["name"], title=state["title"],
                                                         company=state["company"], sources=src_text))])
    return {"profile": profile}


def verify(state: State) -> State:
    """Deterministic checks (no LLM): citations must point to real retrieved URLs."""
    allowed = {s.url for s in state["sources"]}
    p = state["profile"]
    reasons = []
    for fname in FIELDS:
        f = getattr(p, fname)
        if f.value is not None and not f.source_urls:
            reasons.append(f"{fname}: value without citation")
        bad = [u for u in f.source_urls if u not in allowed]
        if bad:
            reasons.append(f"{fname}: cites URL not in retrieved sources {bad}")
    if not reasons:
        return {"verdict": Verdict(status="ok")}
    if state.get("attempts", 0) < MAX_ATTEMPTS:
        return {"verdict": Verdict(status="retry", reasons=reasons),
                "query": f'{state["name"]} {state["company"]} executive biography'}
    return {"verdict": Verdict(status="abstain", reasons=reasons)}


def abstain(state: State) -> State:
    """Blank out every unverifiable field and record why — never fabricate."""
    p = state["profile"]
    allowed = {s.url for s in state["sources"]}
    for fname in FIELDS:
        f = getattr(p, fname)
        f.source_urls = [u for u in f.source_urls if u in allowed]
        if f.value is not None and not f.source_urls:
            f.value, f.note = None, "unverifiable: no retrieved source supports this field"
    return {"profile": p}


def route(state: State) -> str:
    return {"ok": "emit", "retry": "search", "abstain": "abstain"}[state["verdict"].status]


# ---------- graph ----------
def build_graph():
    g = StateGraph(State)
    g.add_node("search", search)
    g.add_node("extract", extract)
    g.add_node("verify", verify)
    g.add_node("abstain", abstain)
    g.add_node("emit", lambda s: {})
    g.add_edge(START, "search")
    g.add_edge("search", "extract")
    g.add_edge("extract", "verify")
    g.add_conditional_edges("verify", route, {"emit": "emit", "search": "search", "abstain": "abstain"})
    g.add_edge("abstain", END)
    g.add_edge("emit", END)
    return g.compile()


def run(name: str, title: str, company: str) -> ExecutiveProfile:
    return build_graph().invoke({"name": name, "title": title, "company": company, "attempts": 0})["profile"]
