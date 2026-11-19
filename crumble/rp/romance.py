"""Romance stages and the romantic beats."""
import re

from .actions import LAB, ROMS
from .dice import TIER_TXT, TIER_UI, check, md
from .relations import adult

ROM_STAGES = [(10, "no romantic spark yet"), (25, "curious, starting to notice them"), (45, "attracted and flirty"),
              (65, "smitten and romantic"), (85, "in love, a couple"), (101, "deeply committed")]


def rom_stage(v):
    return next(l for t, l in ROM_STAGES if v < t)


def romance_beat(act, c, rp, aff, mood, ust, cfg, user, out):
    nm, need = c.get("name") or "They", ROMS[act]
    rom = rp.setdefault("rom", {}).setdefault(c["id"], {"v": 0, "ms": []})
    title = LAB[act][0] + " · CHA"
    a, mt, rt = aff.get(c["id"], 50), str(mood.get(c["id"], "")), (c.get("romance") or "").lower()
    warm = rom["v"] + max(0, a - 50) // 3
    out["acting"] = [c["id"]]
    if need > warm + 25:
        rom["v"], out["aff"][c["id"]] = max(0, rom["v"] - 1), -1
        out["card"] = {"type": act, "title": title, "note": f"Too soon: {nm} isn't ready for this yet.",
                       "rows": [{"who": f"{user} → {nm}", "res": "Too soon", "tier": "fail", "ex": f"💞 {rom_stage(rom['v'])}"}]}
        out["brief"] = (f"[Romantic beat] {user} tries to {LAB[act][0].lower()} with {nm}, but it is far too soon for {nm}'s feelings "
                        f"(they are: {rom_stage(rom['v'])}). {nm} is not ready: they deflect, tease, blush, step back or say so gently, as their personality fits. They do not accept.")
        return
    dc = (10 + max(0, need - warm) // 4 + (4 if a <= 35 else 2 if a < 50 else -2 if a >= 75 else 0)
          + (3 if re.search(r"angry|furious|annoyed|irritated|hurt|sad|upset", mt) else -1 if re.search(r"happy|playful|affectionate|relaxed|joyful|content|flustered|shy", mt) else 0)
          + (2 if re.search(r"slow.?burn|guarded|shy|reserved|hard to get|cautious|aloof|wary|takes time|trust issues", rt)
             else -2 if re.search(r"flirty|bold|forward|romantic|passionate|bubbly|affectionate", rt) else 0)
          + {"easy": -2, "hard": 3}.get(cfg.get("diff"), 0))
    r = check(md(ust["CHA"]), max(6, dc))
    d = {"crit": 6, "win": 3, "part": 1, "fail": -1, "bust": -3}[r["tier"]] + (1 if need >= 50 and r["tier"] in ("crit", "win") else 0)
    rom["v"] = max(0, min(100, rom["v"] + d))
    out["aff"][c["id"]] = {"crit": 3, "win": 2, "part": 0, "fail": -1, "bust": -3}[r["tier"]]
    ms = {"kiss": "first kiss", "confess": "feelings confessed and returned", "date": "went on a date together",
          "intimate": "became intimate (kept tasteful and off-screen)"}.get(act)
    if ms and r["tier"] in ("crit", "win") and ms not in rom["ms"]:
        rom["ms"].append(ms)
    if act == "confess" and r["tier"] in ("fail", "bust") and "confession turned down" not in rom["ms"]:
        rom["ms"].append("confession turned down")
    rom["ms"] = rom["ms"][-8:]
    if adult(c):
        from .intimacy import settings as intim_settings
        icfg = intim_settings(cfg.get("intimacy"))
        if icfg["on"]:
            intim = rp.setdefault("intim", {}).setdefault(c["id"], {"iv": 0, "acts": []})
            if act == "kiss" and r["tier"] in ("crit", "win"):
                intim["iv"] = min(100, intim["iv"] + (4 if r["tier"] == "crit" else 2))
                if "first kiss" not in intim["acts"]:
                    intim["acts"].append("first kiss")
                    intim["acts"] = intim["acts"][-8:]
            elif act == "touch" and r["tier"] in ("crit", "win"):
                intim["iv"] = min(100, intim["iv"] + (2 if r["tier"] == "crit" else 1))
    react = {"crit": f"{nm} is clearly moved and responds warmly, in their own way.",
             "win": f"{nm} welcomes it, in character (shy, teasing, warm: whatever fits them).",
             "part": f"{nm} is torn or flustered: a hesitant, mixed or conditional response, neither a clear yes nor a clear no.",
             "fail": f"{nm} politely or firmly does not go along with it, as their personality dictates, without needless cruelty.",
             "bust": f"It lands badly: awkward or off-putting to {nm}. They react accordingly and the mood cools."}[r["tier"]]
    tone = ("Write it tastefully: imply rather than describe, and cut away (fade to black) before anything explicit. " if act == "intimate"
            else "Keep it sweet and PG. " if cfg.get("tone") == "sweet" else "")
    out["brief"] = (f"[Romantic beat] {user} tries to {LAB[act][0].lower()} with {nm}. Result: {TIER_TXT[r['tier']]}.\n{react}\n"
                    f"{nm}'s feelings toward {user} are now: {rom_stage(rom['v'])}. {tone}")
    out["card"] = {"type": act, "title": title, "rows": [{"who": f"{user} → {nm}", "d": f"d20 {r['roll']}{r['bonus']:+d} = {r['total']} vs DC {max(6, dc)}",
                   "res": TIER_UI[r["tier"]], "tier": r["tier"], "ex": f"💞 {rom_stage(rom['v'])} ({d:+d})"}], "note": ""}
