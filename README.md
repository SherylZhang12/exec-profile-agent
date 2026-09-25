# exec-profile-agent

A LangGraph agent that turns *name + title + company* into a **citation-grounded professional profile**
of a public-company executive — and leaves a field blank rather than invent it.

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
python -m pytest -q             # 8 tests, no keys needed
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
_(fill in after running the evaluation — hand-graded, N executives)_

| mode | precision on answered | coverage | correct abstentions | wrong answers | median latency |
|---|---|---|---|---|---|
| baseline | | | | | |
| rag | | | | | |

## Design notes & known limitations
- The v1 of this system (a research pipeline) enforced "don't fabricate" with prompt rules alone. v2 moves
  enforcement into code: citations are checked deterministically, and the summary is rebuilt from verified fields.
- `verify` checks that a cited URL was retrieved, not that the page *entails* the claim. An entailment check
  (a second model judging claim-vs-chunk) is the next step.
- The summary check covers numbers/years only; it cannot catch an invented name or school.
- Secrets are passed as env vars for simplicity; production should use Secret Manager.
- Only professional, publicly reported information is collected, by design.
