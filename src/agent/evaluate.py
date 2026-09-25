"""Evaluation harness — produces the numbers you can honestly report.

Step 1  run:   python -m src.agent.evaluate run eval/people.csv --modes baseline rag
        → runs every person in both modes, writes eval/results_<mode>.csv
          (one row per person × field) and prints automatic metrics.
Step 2  grade: open each results CSV and fill the `grade` column by hand for every row:
          C = value is correct (you checked it against a reliable source)
          W = value is wrong or about the wrong person
          U = left blank, and you also can't find reliable public info  (correct abstention)
          M = left blank, but reliable public info exists                (missed)
Step 3  score: python -m src.agent.evaluate score eval/results_baseline.csv eval/results_rag.csv
        → precision on answered fields, coverage, missed rate, per mode.
"""
import argparse, csv, statistics, sys, time
from pathlib import Path
from .graph import run
from .schemas import FIELDS

COLS = ["person", "title", "company", "field", "value", "source_urls", "note", "grade"]


def cmd_run(people_csv: str, modes: list[str], pause: float) -> None:
    people = list(csv.DictReader(open(people_csv)))
    for mode in modes:
        rows, lat, calls, errors, grounded, fallbacks = [], [], [], 0, 0, 0
        for i, r in enumerate(people, 1):
            name, title, company = r["name"].strip(), r["title"].strip(), r["company"].strip()
            print(f"[{mode}] {i}/{len(people)} {name}", file=sys.stderr)
            try:
                p = run(name, title, company, mode=mode)
            except Exception as e:  # one failure must not kill the batch
                errors += 1
                rows.append({"person": name, "title": title, "company": company, "field": "ERROR",
                             "value": "", "source_urls": "", "note": repr(e)[:300], "grade": ""})
                continue
            lat.append(p.meta["latency_s"]); calls.append(p.meta["llm_calls"])
            grounded += p.summary_grounded; fallbacks += bool(p.meta.get("summary_fallback"))
            for f in FIELDS + ["summary"]:
                fld = getattr(p, f)
                if f == "summary":
                    rows.append({"person": name, "title": title, "company": company, "field": "summary",
                                 "value": fld, "source_urls": "", "note": "", "grade": ""})
                else:
                    rows.append({"person": name, "title": title, "company": company, "field": f,
                                 "value": fld.value or "", "source_urls": " ".join(fld.source_urls),
                                 "note": fld.note, "grade": ""})
            time.sleep(pause)  # stay under free-tier rate limits
        out = Path(f"eval/results_{mode}.csv")
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader(); w.writerows(rows)
        field_rows = [x for x in rows if x["field"] in FIELDS]
        answered = sum(1 for x in field_rows if x["value"])
        ok = len(people) - errors
        print(f"\n=== {mode} ===  people={len(people)} ok={ok} errors={errors}")
        if field_rows:
            print(f"fields={len(field_rows)} answered={answered} "
                  f"abstention_rate={1 - answered / len(field_rows):.1%}")
        if lat:
            print(f"median_latency={statistics.median(lat):.1f}s  mean_llm_calls={statistics.mean(calls):.1f}  "
                  f"summaries_grounded={grounded}/{ok}  template_fallbacks={fallbacks}")
        print(f"→ wrote {out}; now fill the `grade` column (C/W/U/M) by hand, then run `score`.")


def cmd_score(paths: list[str]) -> None:
    for path in paths:
        rows = [r for r in csv.DictReader(open(path)) if r["field"] in FIELDS]
        g = [r["grade"].strip().upper() for r in rows]
        ungraded = sum(1 for x in g if x not in {"C", "W", "U", "M"})
        C, W, U, M = (g.count(x) for x in "CWUM")
        answered, blank = C + W, U + M
        print(f"\n=== {path} ===  graded={len(g) - ungraded}/{len(g)}")
        if answered:
            print(f"precision on answered fields = {C}/{answered} = {C / answered:.1%}")
        if blank:
            print(f"correct abstentions          = {U}/{blank} = {U / blank:.1%}")
        if C + M:
            print(f"coverage of available facts  = {C}/{C + M} = {C / (C + M):.1%}")
        print(f"wrong answers (fabricated/mismatched) = {W}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("people_csv")
    r.add_argument("--modes", nargs="+", default=["baseline", "rag"]); r.add_argument("--pause", type=float, default=4.0)
    s = sub.add_parser("score"); s.add_argument("paths", nargs="+")
    a = ap.parse_args()
    cmd_run(a.people_csv, a.modes, a.pause) if a.cmd == "run" else cmd_score(a.paths)
