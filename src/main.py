"""CLI:  python -m src.main "Satya Nadella" "CEO" "Microsoft" [--mode rag|baseline]"""
import argparse, json
from src.agent.graph import run

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name"); ap.add_argument("title"); ap.add_argument("company")
    ap.add_argument("--mode", default="rag", choices=["rag", "baseline"])
    a = ap.parse_args()
    print(json.dumps(run(a.name, a.title, a.company, mode=a.mode).model_dump(), indent=2, ensure_ascii=False))
