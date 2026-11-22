"""Turn what the player just did into outcomes, wounds, deaths and relationship changes. No dice, and no fight engine: conflict is story (see story/tension.py);
here only skill attempts, romance, care and resurrection are judged, from skills, condition and situation."""
import json
import re

from . import body as B
from . import skillset as SK
from .actions import AUTO, LAB, ROMS, classify
from .dice import TIER_TXT, TIER_UI, best, best_name, check, edge, parse_stats
from .mentions import find_ids
from .relations import decline, effective
from .romance import romance_beat
from .intimacy import intimacy_beat, settings as intim_settings
from .skills import AFF_FX, skill_dc

SKILL_KEY = {"persuade": "social", "intimidate": "social", "deceive": "social", "comfort": "social", "sneak": "stealth", "steal": "stealth",
             "investigate": "wits", "craft": "wits", "heal": "aid", "athletics": "hp"}


def _ev_text(evs, names):
    out = []
    for e in evs:
        n = names.get(e.get("id"), "They")
        k, p = e.get("k", ""), e.get("p", "")
        if e["ev"] == "healed":
            out.append(f"{n}'s {k}{(' on the ' + p) if p else ''} has healed")
        elif e["ev"] == "eased":
            out.append(f"{n}'s {k}{(' on the ' + p) if p else ''} has eased")
        elif e["ev"] == "worse":
            out.append(f"{n}'s {k} has got worse")
        elif e["ev"] == "died":
            out.append(f"{n} {e['how']}")
    return out


def _pass_time(rp, ids, names, hours, rested, turn, aff, mood, out):
    """Let story time pass for everyone's bodies. Anyone who dies of it is marked dead properly."""
    notes = []
    for cid in ids:
        bd = B.get(rp, cid)
        if bd["dead"]:
            continue
        evs = [dict(e, id=cid) for e in B.tick(bd, hours, rested)]
        for e in evs:
            if e["ev"] == "died":
                B.kill(rp, cid, e["how"], turn, aff.get(cid), mood.get(cid))
                out["deaths"].append(cid)
        notes += _ev_text(evs, names)
    return notes


def _target_dead(c, rp, user, out, act):
    out["acting"] = []
    out["brief"] = (f"[Note] {user} directs something at {c.get('name')}, but {c.get('name')} is dead. Their body cannot answer, react, speak or act. "
                    f"Describe only what {user} does and the stillness of the body; the living may react in their own way.")
    out["card"] = {"type": act or "other", "title": "☠ " + (c.get("name") or "?"), "rows": [{"who": c.get("name") or "?", "res": "Dead", "tier": "fail",
                                                                                             "ex": "Only a resurrection can change this"}], "note": ""}


def rp_resolve(b):
    """Returns the new state, a card for the page and a brief for the model."""
    members, user = b["members"], str(b.get("user") or "User")
    cfg, text, forced = b.get("cfg") or {}, str(b.get("text") or "")[:2000], b.get("forced") or None
    rp = json.loads(json.dumps(b.get("rp") or {}))
    rp.pop("hp", None)       # the old instant-heal hit points are gone: bodies persist in rp["body"]
    aff = {k: int(v) for k, v in (b.get("aff") or {}).items() if isinstance(v, (int, float))}
    mood = {k: str(v) for k, v in (b.get("mood") or {}).items()}
    ust, ugear, uskills = parse_stats(b.get("ustats")), str(b.get("ugear") or "")[:400], str(b.get("uskills") or "")[:1200]
    uprof = SK.parse(uskills, ugear)
    turn = int(b.get("turn") or 0)
    out = {"rp": rp, "card": None, "brief": "", "acting": [], "aff": {}, "deaths": [], "revived": {}, "bodies": {}}
    rp.pop("combat", None)      # the old fight engine is gone: chats saved with a fight in progress simply carry on as a story
    byid = {c["id"]: c for c in members}
    names = {c["id"]: c.get("name") or "They" for c in members}
    names["user"] = user
    tids = find_ids(text, members, True) or find_ids(text, members, False)
    if not tids and b.get("last") in byid:
        tids = [b["last"]]
    if not tids and len(members) == 1:
        tids = [members[0]["id"]]
    ids = ["user"] + [c["id"] for c in members]
    dead_ids = [i for i in ids if B.is_dead(rp, i)]
    note = ""

    def finish():
        for i in ids:
            out["bodies"][i] = B.summary(B.get(rp, i))
        out["acting"] = [i for i in out["acting"] if i not in B.dead_ids(rp)]
        return out

    # ---- time passes (a little with every exchange; a lot when the text says so, or on a rest)
    hours = B.PER_EXCHANGE_H + B.skip_hours(text)
    if forced == "rest":
        hours = max(hours, 8.0)
    tnotes = _pass_time(rp, ids, names, hours, forced == "rest" or hours >= 6, turn, aff, mood, out)
    if forced == "rest":
        left = [f"{names[i]}: {B.cond_phrase(B.get(rp, i))}" for i in ids if not B.is_dead(rp, i) and B.describe(B.get(rp, i))]
        out["brief"] = (f"[Time passes: about {int(hours) if hours >= 2 else 'an'} hour{'s' if hours >= 2 else ''} of rest and recovery.] "
                        + (("Changes: " + "; ".join(tnotes) + ". ") if tnotes else "") + (("Still hurt: " + "; ".join(left) + ". ") if left else "Everyone is in decent shape. ")
                        + "Wounds mend slowly: show only the progress that this much time truly allows.")
        out["card"] = {"type": "rest", "title": "Rest", "rows": [], "note": ("; ".join(tnotes) or "Time passes.")}
        return finish()
    if tnotes:
        note = "[Time has passed: " + "; ".join(tnotes) + ".] "
    if out["deaths"]:
        out["brief"] += f"[Death] {', '.join(names[i] for i in out['deaths'])} died of their condition. Describe it with weight; the others react in their own way. "

    # ---- the author's hand: bring someone back
    if forced == "revive":
        tgt = next((byid[i] for i in tids if B.is_dead(rp, i)), None) or next((byid[i] for i in dead_ids if i in byid), None)
        if not tgt:
            return finish()
        st = B.revive(rp, tgt["id"], 2, full=False)
        out["revived"][tgt["id"]] = st
        out["brief"] = f"[Resurrection] {tgt['name']} returns from the dead by the author's will: awake, shaken, remembering dying. {tgt['name']} reacts as they would."
        out["card"] = {"type": "revive", "title": "Resurrection", "rows": [{"who": tgt["name"], "res": "Returned to life", "tier": "crit", "ex": "frail and shaken"}], "note": ""}
        return finish()

    act = forced or (classify(text, False, bool(cfg.get("romance", True))) if cfg.get("mode", "auto") == "auto" else None)
    if act and not forced and act not in AUTO:
        act = None
    if act in ROMS and not cfg.get("romance", True):
        act = None
    narr = re.sub(r'[“"][^”"]*[”"]', " ", text)

    # ---- resurrection by action
    if act == "revive":
        dead_t = [i for i in (tids or []) if i in byid and B.is_dead(rp, i)] or [i for i in dead_ids if i in byid]
        if not dead_t:
            act = "heal"      # nobody is dead: reviving someone who fainted is just first aid
        else:
            tgt = byid[dead_t[0]]
            rv = SK.derive(uprof)["revive"]
            tech = SK.pick(uprof, text, "revive")
            usr = B.get(rp, "user")
            out["acting"] = []
            if rv >= 2 or (forced == "revive"):
                full = rv >= 5
                st = B.revive(rp, tgt["id"], 1 if full else 3 if rv <= 2 else 2, full=full)
                out["revived"][tgt["id"]] = st
                usr["tired"] = min(100, usr.get("tired", 0) + (30 if full else 55))
                out["acting"] = [tgt["id"]]
                out["brief"] = (f"[Resurrection] {user} brings {tgt['name']} back from the dead{(' with ' + tech['name']) if tech else ''}: {tgt['name']} wakes gasping, "
                                f"cold and disoriented, " + ("whole again but shaken" if full else "alive but terribly frail and in pain") + f", remembering dying. It costs {user} dearly: they are drained. "
                                f"{tgt['name']} reacts to coming back, and to {user}, in their own way.")
                out["card"] = {"type": "revive", "title": "Resurrection" + (f" · {tech['name']}" if tech else ""),
                               "rows": [{"who": f"{user} → {tgt['name']}", "res": "Returned to life", "tier": "crit" if full else "win", "ex": "whole" if full else "frail and shaken"}], "note": f"{user} is drained."}
            else:
                usr["tired"] = min(100, usr.get("tired", 0) + 20)
                out["brief"] = (f"[Resurrection failed] {user} tries to bring {tgt['name']} back, but has no real power to do it. Nothing happens: the body stays still and cold. "
                                f"Show the desperate attempt failing, and its emotional weight.")
                out["card"] = {"type": "revive", "title": "Resurrection", "rows": [{"who": f"{user} → {tgt['name']}", "res": "Nothing happens", "tier": "fail",
                                                                                     "ex": "no power to raise the dead"}], "note": "Only someone with true revival power (or the author) can do this."}
            return finish()

    # ---- the dead cannot be fought, talked to or courted
    if act and act != "revive" and tids:
        t0 = byid.get(tids[0])
        if t0 and B.is_dead(rp, t0["id"]):
            _target_dead(t0, rp, user, out, act)
            return finish()

    if act in ROMS:
        c = byid.get(tids[0]) if tids else None
        if c:
            path = effective(c, (rp.get("rel") or {}).get(c["id"]))
            if path not in ("auto", "romance"):
                decline(act, c, rp, user, out, path)
                return finish()
            icfg = intim_settings(cfg.get("intimacy"))
            if act == "intimate" and icfg["on"]:
                intimacy_beat(act, c, rp, aff, mood, ust, cfg, icfg, user, out)
            else:
                romance_beat(act, c, rp, aff, mood, ust, cfg, user, out)
            bdc = B.penalty(B.get(rp, c["id"]))
            if B.describe(B.get(rp, c["id"])) and out.get("brief"):
                out["brief"] += f" {c['name']} is hurt or unwell right now, which weighs on how they respond."
        out["brief"] = note + out.get("brief", "")
        return finish()
    elif act in LAB:
        tgt = byid.get(tids[0]) if tids and act in ("persuade", "intimidate", "deceive", "comfort", "sneak", "steal", "heal") else None
        self_heal = act == "heal" and (re.search(r"(?i)\b(?:myself|my own|my wounds?|my (?:arm|leg|side)|me\b)", narr) or not tgt)
        tech = SK.pick(uprof, text, act)
        dv = SK.derive(uprof)
        sk = dv.get(SKILL_KEY.get(act, ""), 0)
        tact = SK.tactics(text)
        usr = B.get(rp, "user")
        pen = B.penalty(usr)
        bonus = best(ust, LAB[act][1]) + sk + tact - pen["all"] - (pen["atk"] // 2 if act in ("craft", "steal", "heal") else 0) - usr.get("tired", 0) // 40
        dc = skill_dc(act, tgt, aff, mood, cfg)
        if act == "heal":
            tb = B.get(rp, "user") if self_heal else (B.get(rp, tgt["id"]) if tgt else None)
            dc = 9 + (2 if tb and any(i["s"] >= 3 for i in tb["inj"] + tb["ill"]) else 0) + (3 if tb and B.bleeding(tb) else 0)
        r = check(bonus, dc)
        label = LAB[act][0]
        who = f" {tgt['name']}" if tgt else ""
        way = f" using {tech['name']}" if tech else ""
        out["brief"] = note + f"[Action resolved] {user} tries to {label.lower()}{(' (on' + who + ')') if tgt else ''}{way}: {TIER_TXT[r['tier']]}. Show it playing out that way; do not contradict this outcome."
        ex = ""
        if act == "heal":
            tb = B.get(rp, "user") if self_heal else (B.get(rp, tgt["id"]) if tgt else None)
            patient = user if self_heal or not tgt else tgt["name"]
            if tb is not None and r["tier"] in ("crit", "win", "part"):
                done = B.treat(tb, 4 if r["tier"] == "crit" and dv["aid"] >= 3 else 2 if r["tier"] == "win" else 1)
                if done:
                    out["brief"] += f" What was actually done for {patient}: {'; '.join(done)}. They are still hurt and will need time and rest to mend."
                    ex = "; ".join(done)[:60]
                else:
                    out["brief"] += f" {patient} has no wounds or illness that need treating."
                    ex = "nothing to treat"
            elif tb is not None:
                out["brief"] += f" {patient}'s condition is not improved; the attempt does not help (or makes it hurt)."
        out["card"] = {"type": act, "title": f"{label} · {tech['name'] if tech else best_name(ust, LAB[act][1])}", "note": "",
                       "rows": [{"who": f"{user}{' → ' + tgt['name'] if tgt else ''}", "d": edge(r), "res": TIER_UI[r["tier"]], "tier": r["tier"], **({"ex": ex} if ex else {})}]}
        if tgt:
            out["acting"] = [tgt["id"]] if act in ("persuade", "intimidate", "deceive", "comfort", "heal") else []
            fx = AFF_FX.get(act)
            if fx:
                out["aff"][tgt["id"]] = fx[("crit", "win", "part", "fail", "bust").index(r["tier"])]
            if act == "heal" and r["tier"] in ("crit", "win"):
                out["aff"][tgt["id"]] = out["aff"].get(tgt["id"], 0) + 2
        return finish()
    else:
        out["brief"] = note.strip()
        return finish()


def rp_observe(b):
    """Read what a piece of narration says happened to bodies (a wound, a sickness, a death) and how much story time passed, and keep it.
    Dialogue is ignored; negations and near-misses are skipped. Deaths set aside the mood and bond; the dead are never resurrected here."""
    members, user = b["members"], str(b.get("user") or "User")
    rp = json.loads(json.dumps(b.get("rp") or {}))
    rp.pop("hp", None)
    text = str(b.get("text") or "")[:4000]
    aff = {k: int(v) for k, v in (b.get("aff") or {}).items() if isinstance(v, (int, float))}
    mood = {k: str(v) for k, v in (b.get("mood") or {}).items()}
    turn = int(b.get("turn") or 0)
    names = {c["id"]: c.get("name") or "They" for c in members}
    names["user"] = user
    out = {"rp": rp, "events": [], "deaths": [], "bodies": {}}
    ids = ["user"] + [c["id"] for c in members]
    hrs = B.skip_hours(text)
    if hrs:
        _pass_time(rp, ids, names, hrs, hrs >= 6, turn, aff, mood, out)
    for ev in B.observe(text, [c for c in members if not B.is_dead(rp, c["id"])], user):
        cid = ev["id"]
        bd = B.get(rp, cid)
        if bd["dead"]:
            continue
        if ev["what"] == "injury":
            B.add_injury(bd, ev["kind"], ev.get("part"), ev["sev"])
        elif ev["what"] == "illness":
            B.add_illness(bd, ev["kind"], ev["sev"])
        elif ev["what"] == "death" and cid != "user":
            B.kill(rp, cid, "died", turn, aff.get(cid), mood.get(cid))
            if cid not in out["deaths"]:
                out["deaths"].append(cid)
        out["events"].append(dict(ev, name=names.get(cid)))
    for i in ids:
        out["bodies"][i] = B.summary(B.get(rp, i))
    return out
