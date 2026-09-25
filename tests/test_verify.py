"""Unit tests for the reliability gate — run with `pytest`. No API keys needed."""
from src.agent.schemas import Source, ExecutiveProfile, Field_
from src.agent.graph import verify, abstain


def _state(profile, urls):
    return {"sources": [Source(url=u) for u in urls], "profile": profile, "attempts": 5}


def test_ok_when_every_value_is_cited():
    p = ExecutiveProfile(name="A", title="CEO", company="X",
                         current_role=Field_(value="CEO of X", source_urls=["https://x.com/a"]))
    assert verify(_state(p, ["https://x.com/a"]))["verdict"].status == "ok"


def test_uncited_value_is_caught():
    p = ExecutiveProfile(name="A", title="CEO", company="X", education=Field_(value="MIT"))
    v = verify(_state(p, ["https://x.com/a"]))["verdict"]
    assert v.status == "abstain" and "education" in v.reasons[0]


def test_hallucinated_url_is_caught_and_blanked():
    p = ExecutiveProfile(name="A", title="CEO", company="X",
                         education=Field_(value="MIT", source_urls=["https://made-up.com"]))
    s = _state(p, ["https://x.com/a"])
    assert verify(s)["verdict"].status == "abstain"
    out = abstain(s)["profile"]
    assert out.education.value is None and "unverifiable" in out.education.note
