"""Ability scores, d20 checks and the outcome tiers."""
import random
import re

ABIL = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
TIER_TXT = {"crit": "CRITICAL SUCCESS: it works even better than hoped", "win": "SUCCESS",
            "part": "PARTIAL SUCCESS: it works only in part, or with a cost or complication",
            "fail": "FAILURE: it does not work, and there is a consequence", "bust": "CRITICAL FAILURE: it backfires badly"}
TIER_UI = {"crit": "Critical success", "win": "Success", "part": "Partial", "fail": "Failure", "bust": "Critical failure"}


def parse_stats(txt):
    s = {k: 10 for k in ABIL}
    for k, v in re.findall(r"\b(STR|DEX|CON|INT|WIS|CHA)\w*\W{0,3}(\d{1,2})\b", (txt or "").upper()):
        s[k] = max(3, min(20, int(v)))
    return s


def md(v):
    return (int(v) - 10) // 2


def roll(n, s):
    return sum(random.randint(1, s) for _ in range(n))


def check(bonus, dc, adv=0):
    a, b = random.randint(1, 20), random.randint(1, 20)
    r = max(a, b) if adv > 0 else min(a, b) if adv < 0 else a
    t = r + bonus
    tier = "crit" if r == 20 else "bust" if r == 1 else "win" if t >= dc else "part" if t >= dc - 3 else "fail"
    return {"roll": r, "bonus": bonus, "total": t, "dc": dc, "tier": tier}


def best(ust, abils):
    return max((md(ust[a]) for a in abils), default=0)


def best_name(ust, abils):
    return max(abils, key=lambda a: ust[a]) if abils else ""
