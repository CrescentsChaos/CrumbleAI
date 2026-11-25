"""Which retry rules earn their keep?  python -m tools.retry_stats [path/to/retry_log.jsonl]

Reads data/retry_log.jsonl (one line per reply that tripped a rule: names and timings, never text) and counts, per rule, how often it
tripped, how often it caused a new generation, and how often it was held back (budget / attempt cap). A rule that trips a lot and is
never in HARD_RETRY (crumble/llm.py) costs nothing; a rule in HARD_RETRY that fires on a large share of replies is the one to look at.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(path=None):
    f = Path(path) if path else ROOT / "data" / "retry_log.jsonl"
    if not f.exists():
        print("no log yet:", f)
        return
    n, rules, ms = 0, defaultdict(lambda: dict(seen=0, retried=0, budget=0, cap=0)), []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        n += 1
        ms.append(e.get("ms", 0))
        for ev in e.get("events", []):
            for r in ev.get("rules", []):
                d = rules[r]
                d["seen"] += 1
                d["retried"] += bool(ev.get("retried"))
                d[ev.get("why_not") or "none"] = d.get(ev.get("why_not") or "none", 0) + (1 if ev.get("why_not") else 0)
    print(f"{n} replies tripped at least one rule; median time spent on them {sorted(ms)[len(ms) // 2] / 1000:.1f}s\n")
    print(f"{'rule':28s}{'tripped':>9s}{'retried':>9s}{'budget':>8s}{'cap':>6s}")
    for r, d in sorted(rules.items(), key=lambda kv: -kv[1]["retried"] * 1000 - kv[1]["seen"]):
        print(f"{r:28s}{d['seen']:9d}{d['retried']:9d}{d['budget']:8d}{d['cap']:6d}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
