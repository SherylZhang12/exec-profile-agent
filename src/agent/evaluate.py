"""Phase 4: measure the thing you'll put on your resume.

Run the agent over a labeled set of executives and report:
  - citation validity  : % of non-null fields whose cited URL really contains the claim (you label this)
  - abstention rate    : % of fields left blank (higher is fine; it means no fabrication)
  - field accuracy     : % of non-null fields that match your hand-checked label
Put 20-30 executives in eval/labels.json:  {"Satya Nadella|CEO|Microsoft": {"education": "...", ...}}
"""
import json, sys
from .graph import run, FIELDS


def main(path: str = "eval/labels.json"):
    labels = json.load(open(path))
    n_fields = n_nonnull = n_correct = 0
    for key, truth in labels.items():
        name, title, company = key.split("|")
        p = run(name, title, company)
        for f in FIELDS:
            n_fields += 1
            v = getattr(p, f).value
            if v is None:
                continue
            n_nonnull += 1
            if truth.get(f) and truth[f].lower() in v.lower():
                n_correct += 1
    print(f"fields={n_fields} answered={n_nonnull} abstained={n_fields-n_nonnull} "
          f"accuracy_on_answered={n_correct/max(n_nonnull,1):.1%} abstention_rate={(n_fields-n_nonnull)/n_fields:.1%}")


if __name__ == "__main__":
    main(*sys.argv[1:])
