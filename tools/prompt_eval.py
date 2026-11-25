"""Golden-set check for the prompt: does a shorter prompt make the replies worse?

  python -m tools.prompt_eval --model models/X.gguf --out before.json     # run on the OLD project, then again on the NEW one
  python -m tools.prompt_eval --compare before.json after.json            # side by side
  python -m tools.prompt_eval --dry                                       # no model: just the prompt sizes per tier

Every conversation in tests/golden/conversations.json is answered --n times. Each reply is scored with the detectors the app already has:
assistant-speak (AI_HARD / AI_SOFT), a closing question, writing for the user, list formatting, and length. Lower is better except words.
"""
import argparse
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from crumble.config import model_tier                       # noqa: E402
from crumble.personality import lexicon as L                # noqa: E402
from crumble.prompt import build_messages                   # noqa: E402

GOLD = ROOT / "tests" / "golden" / "conversations.json"


def score(text, user):
    t = text.strip()
    puppet = bool(re.search(r"\*[^*\n]*\b%s\b[^*\n]*\*" % re.escape(user), t)) or bool(re.search(r"(?m)^%s\s*:" % re.escape(user), t))
    return {"ai": int(bool(L.AI_HARD.search(t) or L.AI_SOFT.search(t))), "question_end": int(t.rstrip("*_ \"").endswith("?")),
            "puppet": int(puppet), "list": int(bool(L.LIST_LINE.search(t))), "words": len(t.split())}


def prompts(tier=None):
    for g in json.loads(GOLD.read_text(encoding="utf-8")):
        o = {"mode": g.get("mode", "story"), "state": {}, "words": (20, 80)}
        if tier is not None:
            o["tier"] = tier
        yield g, build_messages(g["char"], g["user"], g["history"], o)


def run(a):
    from llama_cpp import Llama
    llm = Llama(model_path=a.model, n_ctx=a.ctx, n_gpu_layers=-1, verbose=False)
    tier = model_tier(a.model)
    rows = []
    for g, msgs in prompts(None if a.tier is None else a.tier):
        for _ in range(a.n):
            r = llm.create_chat_completion(messages=msgs, max_tokens=220, temperature=.8)
            rows.append(dict(id=g["id"], **score(r["choices"][0]["message"]["content"], g["user"])))
    out = {"model": Path(a.model).name, "tier": tier, "prompt_tokens": len(llm.tokenize(msgs[0]["content"].encode())), "n": len(rows), "rows": rows}
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    summary(out)


def summary(d):
    r = d["rows"]
    print(f"{d['model']}  tier {d['tier']}  system prompt ~{d['prompt_tokens']} tokens  {d['n']} replies")
    for k in ("ai", "question_end", "puppet", "list"):
        print(f"  {k:13s} {sum(x[k] for x in r) / len(r):5.0%}")
    print(f"  {'words (median)':13s} {st.median(x['words'] for x in r):5.0f}")


def compare(a, b):
    A, B = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (a, b))
    print(f"{'':14s}{'before':>9s}{'after':>9s}")
    for k in ("ai", "question_end", "puppet", "list"):
        x, y = (sum(r[k] for r in d["rows"]) / len(d["rows"]) for d in (A, B))
        print(f"{k:14s}{x:9.0%}{y:9.0%}   {'WORSE' if y > x + .05 else ''}")
    print(f"{'prompt tokens':14s}{A['prompt_tokens']:9d}{B['prompt_tokens']:9d}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model"); p.add_argument("--out", default="eval.json"); p.add_argument("--n", type=int, default=5)
    p.add_argument("--ctx", type=int, default=8192); p.add_argument("--tier", type=int, choices=(0, 1, 2))
    p.add_argument("--compare", nargs=2); p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    if a.compare:
        compare(*a.compare)
    elif a.dry or not a.model:
        for t in (0, 1, 2):
            sizes = [len(m[0]["content"]) // 4 for _, m in prompts(t)]
            print(f"tier {t}: system prompt ~{int(st.median(sizes))} tokens")
    else:
        run(a)
