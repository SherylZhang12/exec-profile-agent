# Evaluation

The evaluation set and graded results are kept **private** (the executive list was drawn from a
research dataset that is not mine to publish). The harness is fully reproducible with your own list:

1. Create `eval/people.csv` with columns `name,title,company` (20-25 executives; mix well-known,
   obscure, and common-name cases).
2. `python -m src.agent.evaluate run eval/people.csv --modes baseline rag`
3. Fill each row's `grade` column: C (correct) / W (wrong) / U (correct blank) / M (missed), then
   `python -m src.agent.evaluate score eval/results_baseline.csv eval/results_rag.csv`
4. For the stale-role check, create `eval/status_truth.csv`
   (`name,company,truth,still_at_company,confidence,evidence`) and run
   `python -m src.agent.evaluate status eval/results_rag.csv`

`eval/*.csv` is git-ignored so data never gets committed by accident.
