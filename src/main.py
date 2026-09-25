"""CLI: python -m src.main "Satya Nadella" "CEO" "Microsoft"  -> prints JSON profile."""
import json, sys
from src.agent.graph import run

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit('usage: python -m src.main "<name>" "<title>" "<company>"')
    p = run(*sys.argv[1:])
    print(json.dumps(p.model_dump(), indent=2, ensure_ascii=False))
