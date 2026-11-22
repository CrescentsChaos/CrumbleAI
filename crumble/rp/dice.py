"""Ability scores and DETERMINISTIC outcome judging. There is no dice rolling anywhere in Crumble.

An attempt is judged by comparing what the doer brings (ability, trained skill, how well they described the move, their health and
momentum) against what stands in the way (difficulty, guard, the other side's condition). The same situation always gives the same
outcome, and a different situation (a wounded arm, a better plan, a tired fighter) gives a different one.

    judge(power, resist)  ->  {"power", "resist", "margin", "tier"}          tier: crit | win | part | fail | bust
    check(bonus, dc, adv) ->  same, with the old key names (roll/bonus/total/dc) so every caller keeps working
"""
import re

ABIL = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
TIER_TXT = {"crit": "CRITICAL SUCCESS: it works even better than hoped", "win": "SUCCESS",
            "part": "PARTIAL SUCCESS: it works only in part, or with a cost or complication",
            "fail": "FAILURE: it does not work, and there is a consequence", "bust": "CRITICAL FAILURE: it backfires badly"}
TIER_UI = {"crit": "Overwhelming", "win": "Success", "part": "Partial", "fail": "Failure", "bust": "Backfires"}
BASE = 11     # what an untrained, unhurt person brings to an ordinary task


def parse_stats(txt):
    s = {k: 10 for k in ABIL}
    for k, v in re.findall(r"\b(STR|DEX|CON|INT|WIS|CHA)\w*\W{0,3}(\d{1,2})\b", (txt or "").upper()):
        s[k] = max(3, min(20, int(v)))
    return s


def md(v):
    return (int(v) - 10) // 2


def avg(n, s):
    """The average of n dice of s sides, as a fixed number (damage is never random)."""
    return n * (s + 1) // 2


roll = avg      # old name, kept so older callers still import; it is a fixed average now


def tier_of(margin):
    return "crit" if margin >= 8 else "win" if margin >= 0 else "part" if margin >= -3 else "fail" if margin >= -9 else "bust"


def judge(power, resist):
    m = int(power) - int(resist)
    return {"power": int(power), "resist": int(resist), "margin": m, "tier": tier_of(m)}


def check(bonus, dc, adv=0):
    """A deterministic attempt: BASE + bonus (+3 per advantage step) against dc."""
    t = BASE + int(bonus) + 3 * int(adv)
    r = judge(t, dc)
    return {"roll": BASE + 3 * int(adv), "bonus": int(bonus), "total": t, "dc": int(dc), "tier": r["tier"], "margin": r["margin"]}


def edge(r):
    """Short text for the outcome card, e.g. 'edge +3' (no dice, just how far ahead or behind the attempt was)."""
    m = r.get("margin", 0)
    return f"{'edge' if m >= 0 else 'short by'} {abs(m)}"


def best(ust, abils):
    return max((md(ust[a]) for a in abils), default=0)


def best_name(ust, abils):
    return max(abils, key=lambda a: ust[a]) if abils else ""
