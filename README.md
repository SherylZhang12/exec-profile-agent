# exec-profile-agent

A LangGraph agent that turns *name + title + company* into a **citation-grounded professional profile**
of a public-company executive — and leaves a field blank rather than invent it.

## Why this exists

Research on corporate leaders — for example, studying how executives' backgrounds relate to firm
decisions, or building persona / "digital twin" simulations of decision-makers — needs structured
background data on hundreds or thousands of people. Collecting it by hand does not scale.
Asking an LLM directly is fast but unsafe: models fill gaps with plausible-sounding facts and
citations that were never retrieved, and bad inputs silently corrupt every downstream analysis.

This project takes the middle path: automate the collection (about 15 seconds per profile), but make
every fact traceable to a page the system actually retrieved, and leave a field blank when the
evidence is missing. The goal is data a researcher can use without re-checking every line —
and an evaluation that shows how close it gets.

```
START → search → retrieve → extract → verify ─┬─ ok      → summarize → END
            ▲                                 ├─ retry   → search  (max 2 attempts)
            └─────────────────────────────────┘
                                              └─ abstain → abstain → summarize → END
```

| Node | What it does | Why |
|---|---|---|
| `search` | Tavily web search; drops user-generated domains (Scribd, Reddit, social…); merges results across retries | evidence quality |
| `retrieve` | **rag**: chunk full pages → Chroma → retrieve per field. **baseline**: first 400 chars of each snippet | targeted evidence instead of page openings |
| `extract` | Gemini structured output; identity fields locked to the input | the model can't rename the person |
| `verify` | **deterministic, no LLM**: every cited URL must be one we actually retrieved | a model can't grade its own citations |
| `abstain` | blanks fields whose citations fail, records why | never fabricate |
| `summarize` | LLM writes the summary from *verified fields only*; any number/year not in those fields → retry → template fallback | the summary can't smuggle in unverified facts |

## Run

```bash
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env            # add GOOGLE_API_KEY and TAVILY_API_KEY
python -m pytest -q             # 11 tests, no keys needed
python -m src.main "Satya Nadella" "CEO" "Microsoft"                  # rag mode
python -m src.main "Satya Nadella" "CEO" "Microsoft" --mode baseline  # v1 behaviour
```

If the model name 404s, list what your key can use:
```bash
python -c "from google import genai; import os; from dotenv import load_dotenv; load_dotenv(); c=genai.Client(api_key=os.environ['GOOGLE_API_KEY']); [print(m.name) for m in c.models.list() if 'flash' in m.name]"
```

## Evaluate (baseline vs rag)

See `eval/README.md` for how to build the 20–25 person set.
```bash
python -m src.agent.evaluate run eval/people.csv --modes baseline rag
# hand-grade the `grade` column in eval/results_*.csv: C / W / U / M
python -m src.agent.evaluate score eval/results_baseline.csv eval/results_rag.csv
```

## Deploy (Cloud Run)

```bash
gcloud run deploy exec-profile-agent --source . --region us-east1 --allow-unauthenticated \
  --memory 2Gi --set-env-vars GOOGLE_API_KEY=...,TAVILY_API_KEY=...,GEMINI_MODEL=gemini-3.5-flash-lite
curl -X POST "$URL/profile" -H 'content-type: application/json' \
  -d '{"name":"Satya Nadella","title":"CEO","company":"Microsoft"}'
```

## Results

**v2 evaluation — 25 executives, baseline vs rag**

The set mixes 8 well-known execs, 12 obscure ones (no Wikipedia, no official bio) and 4 common
names; most are *former* CEOs, which turned out to matter. Grading was LLM-assisted, then
cross-checked against an independent reference dataset (a separately built research profile set for
the same executives): the two agreed on 45 of 46 comparable rows, and the one disagreement was
corrected. Rows neither source could verify stay marked `?` and are excluded rather than guessed.

| metric (excl. `current_role`) | baseline | rag |
|---|---|---|
| precision on answered fields | 97.5% (78/80) | 96.4% (80/83) |
| coverage of available facts | 85.7% | **95.2%** |
| `education` coverage | 62.5% | **96.0%** |
| median latency | 7.7 s | 12.5 s |

RAG's gain is coverage at roughly equal precision — mostly because the facts (schools, degrees) sit
deep in full pages that the baseline's 400-character snippets never see.

**What the eval exposed — stale "current" roles.** Full-page retrieval also pulls in old bios written in
the present tense ("X is Chairman and CEO"), so RAG reported former or deceased executives as current:

| stale "current" claims (former/deceased execs) | baseline | rag (v2) | rag (v3) |
|---|---|---|---|
| auto-scored vs a verified ground-truth list | 4/20 | 10/20 | **0/20** |

v3 `role_status` accuracy: 24/25 (96%). The one miss: a CEO who stepped down but stayed on as executive chairman was labeled current — status is per title, not per company.

**v3 fix.** A `role_status` field (`current` / `former` / `deceased`) with its own citation; a prompt rule
that the most recent dated evidence wins; an extra retrieval query for succession/retirement evidence;
and a deterministic rule in code that blanks `current_role` whenever the status is former or deceased.

```bash
python -m src.agent.evaluate run eval/people.csv --modes rag --tag _v3
python -m src.agent.evaluate status eval/results_rag_graded.csv eval/results_rag_v3.csv
```

## Design notes & known limitations
- The v1 of this system (a research pipeline) enforced "don't fabricate" with prompt rules alone. v2 moves
  enforcement into code: citations are checked deterministically, and the summary is rebuilt from verified fields.
- `verify` checks that a cited URL was retrieved, not that the page *entails* the claim. An entailment check
  (a second model judging claim-vs-chunk) is the next step.
- The summary check covers numbers/years only; it cannot catch an invented name or school.
- Secrets are passed as env vars for simplicity; production should use Secret Manager.
- Small sample (25 people): differences are directional, not statistically significant.
- Only professional, publicly reported information is collected, by design.
