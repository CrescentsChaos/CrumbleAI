"""Difficulty of social/skill checks and how they move affection."""
import re

from .dice import md, parse_stats


def skill_dc(act, tgt, aff, mood, cfg):
    base = {"easy": 10, "normal": 12, "hard": 15}.get(cfg.get("diff"), 12)
    if not tgt:
        return base
    s, a, m = parse_stats(tgt.get("stats")), aff.get(tgt["id"], 50), str(mood.get(tgt["id"], ""))
    adj = base - 12
    if act == "persuade":
        return max(6, 11 + md(s["WIS"]) + (50 - a) // 12 + (2 if re.search(r"angry|furious|annoyed|irritated|hostile", m) else 0) + adj)
    if act == "intimidate":
        return max(6, 11 + max(md(s["WIS"]), md(s["CON"])) + (2 if a >= 75 else 0) + adj)
    if act == "deceive":
        return max(6, 11 + md(s["WIS"]) + (2 if re.search(r"skeptic|suspic|wary", m) else 0) + adj)
    if act in ("sneak", "steal"):
        return max(6, base + md(s["WIS"]))
    return base


AFF_FX = {"persuade": (2, 1, 0, -1, -2), "intimidate": (-4, -3, -1, -2, -4), "deceive": (0, 0, 0, -1, -4), "comfort": (3, 2, 1, 0, -1)}   # crit, win, part, fail, bust
