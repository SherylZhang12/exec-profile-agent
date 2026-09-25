# exec-profile-agent

A LangGraph agent that builds **citation-grounded executive profiles** from public web sources, using Gemini for extraction. Given a name, title, and company, it searches the web, extracts structured fields, and verifies that every claim is backed by a source it actually retrieved. Fields it cannot verify are left blank with a reason instead of being guessed.

## Why I built this

I previously built an LLM + web-search pipeline for a research project at Columbia Business School that generated background profiles for ~1,700 S&P 500 executives. That version relied on prompt instructions ("never fabricate", "cite reputable sources") to keep the model honest, and I found that wasn't enough: a model told to cite sources will sometimes produce citations that look right but don't exist in what it retrieved.

This project is a rebuild with one main change: **reliability is enforced in code, not in the prompt.** Verification is a deterministic step in the graph, so the model can't talk its way past it.

## How it works

```
START → search → extract → verify ─┬─ ok      → emit → END
                    ▲              ├─ retry   → search   (bounded, max 2 attempts)
                    └──────────────┘
                                   └─ abstain → abstain → END
```

| Node | What it does |
|---|---|
| `search` | Queries the web (Tavily) for sources about the target person |
| `extract` | Gemini fills a Pydantic schema via structured output; every non-null field must cite source URLs |
| `verify` | Pure Python, no LLM. Checks that each cited URL appears in the retrieved results and that no value is uncited |
| `abstain` | Strips citations that weren't retrieved, blanks unsupported fields, and records why |

A few design decisions:

- **Verification doesn't use an LLM.** It's deterministic, cheap, and can't be persuaded by the output it's checking.
- **Retries are bounded** (`MAX_ATTEMPTS = 2`) with a refined query, so a hard case ends in abstention rather than an expensive loop.
- **Blank beats wrong.** A null field with a note is treated as a correct outcome, not a failure.
- **Professional information only.** The schema covers current role, education, prior roles, board seats, and notable facts. It deliberately excludes personal details.
- **Transient API errors** (e.g., 503 under load) are handled with client-side exponential-backoff retries and a timeout.

## Example output

```
python -m src.main "Satya Nadella" "CEO" "Microsoft"
```

```json
{
  "current_role": {
    "value": "Chairman and Chief Executive Officer of Microsoft",
    "source_urls": ["https://en.wikipedia.org/wiki/Satya_Nadella",
                    "https://news.microsoft.com/source/exec/satya-nadella"]
  },
  "board_seats": {
    "value": null,
    "source_urls": [],
    "note": "No board seats mentioned in the sources."
  }
}
```
(truncated; full output includes education, prior roles, notable facts, and a summary)

## Known issues

Found on the first real runs; tracked as the next things to fix:

1. **The summary isn't verified.** `verify` checks the five structured fields but not `summary`, so the summary can include details (e.g., a specific month) that no field or source supports.
2. **Low-specificity, low-quality evidence.** Sources are truncated to 400 characters before extraction, so specifics that appear later on a page (like school names) never reach the model, and weaker sources (user-uploaded documents) can be cited. Planned fix: per-field vector retrieval over full page content, plus source-quality ranking.
3. **Identity fields can drift.** The model rewrote the input title ("CEO" → "Chairman and Chief Executive Officer"). Name, title, and company should be locked to the input.
4. **`note` is overused.** It should only explain abstentions, but the model restates the value in it.

## Setup

Requires Python 3.11+.

```bash
git clone https://github.com/SherylZhang12/exec-profile-agent.git
cd exec-profile-agent
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

cp .env.example .env
# GOOGLE_API_KEY  — https://aistudio.google.com/apikey
# TAVILY_API_KEY  — https://app.tavily.com
```

Run the tests (no API keys needed):

```bash
python -m pytest -q
```

Run the agent:

```bash
python -m src.main "<name>" "<title>" "<company>"
```

## Project structure

```
src/
  agent/
    graph.py      # LangGraph nodes, routing, and graph assembly
    schemas.py    # Pydantic models: Source, Field_, ExecutiveProfile, Verdict
    prompts.py    # Extraction prompt
    tools.py      # Web search + Gemini client (with retries)
    rag.py        # Chroma vector store (in progress)
    evaluate.py   # Evaluation harness (in progress)
  main.py         # CLI
  api.py          # FastAPI service (in progress)
tests/
  test_verify.py  # Unit tests for the verify/abstain gate
```

## Roadmap

- [x] Search → extract → verify → abstain graph with bounded retry
- [x] Deterministic citation verification with unit tests
- [ ] Verify the summary against cited fields
- [ ] Per-field vector retrieval (Chroma) over full page content
- [ ] Evaluation on a hand-labeled set: accuracy on answered fields, abstention rate, citation validity
- [ ] FastAPI service deployed on Google Cloud Run

## Stack

Python · LangGraph · LangChain · Gemini API · Tavily · Pydantic · pytest · (planned) Chroma, FastAPI, Docker, Cloud Run
