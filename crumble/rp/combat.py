"""Turn-based fights with NO dice: units built from stats, the skills the player (or the character sheet) describes and the real state of their
bodies; deterministic strikes; NPCs that act from morale and sense; wounds that stay after the fight; and the round narration.

An attack is judged by comparing the attacker's power (ability + the technique actually used + how well the move was described + momentum,
minus wounds and tiredness) with the target's guard. Damage is a fixed number from weapon, strength and technique, scaled by how clean the hit was.
Every damaging hit leaves a lasting wound (rp["body"]). A fighter at zero goes down bleeding, or dies if the blow was meant to kill.
"""
import re

from . import body as B
from . import skillset as SK
from .actions import LAB
from .dice import TIER_TXT, TIER_UI, avg, best, best_name, check, edge, md, parse_stats

LETHAL = re.compile(r"(?i)\b(?:kill\w*|slay\w*|murder\w*|behead\w*|decapitat\w*|execut\w*|finish (?:him|her|them|it|the \w+) off|end (?:him|her|them|it)\b|put (?:him|her|them) down|slit \w+ throat|cut \w+ throat|impale\w*|stab\w* (?:him|her|them|\w+) (?:in|through) the (?:heart|chest|neck|throat)|to the death|strangl\w*|snap\w* (?:his|her|their) neck)")
MERCY = re.compile(r"(?i)\b(?:spare\w*|non-?lethal|knock\w* (?:him|her|them|\w+) out|subdue\w*|disarm\w*|without killing|not to kill|incapacitat\w*|flat of (?:the|my) blade|stun\w*)\b")
WK = [("gun", r"rifle|shotgun|sniper|pistol|gun|revolver|cannon|firearm|musket|blaster"), ("bow", r"crossbow|\bbow\b|longbow|arrow"),
      ("blade", r"sword|blade|katana|saber|sabre|rapier|dagger|knife|knives|scimitar|machete|claymore|scythe|sickle|stiletto|axe|glaive|halberd|spear|lance|trident|kunai"),
      ("heavy", r"hammer|mace|club|\bbat\b|staff|maul|flail|chain|whip|baton|crowbar|pipe"), ("claws", r"claws?|fangs?|talons?"),
      ("unarmed", r"fists?|punch|kick|martial|karate|boxing|judo|kung|brawl|wrestl|unarmed|knuckles|headbutt|elbow|knee")]


def weapon_die(txt):
    t = (txt or "").lower()
    for pat, d in ((r"greatsword|greataxe|warhammer|maul|halberd|rifle|shotgun|sniper|cannon|scythe|battleaxe|axe|hammer|claymore", 10),
                   (r"sword|blade|katana|saber|sabre|mace|spear|rapier|pistol|gun|revolver|crossbow|bow|whip|staff|bat|club|trident|chain|scimitar|machete", 8),
                   (r"dagger|knife|claws?|fangs?|talons?|stiletto|dart|sling|taser|baton|brass knuckles|kunai", 6)):
        if re.search(r"\b(?:%s)\b" % pat, t):
            return d
    return 4


def weapon_kind(txt):
    t = (txt or "").lower()
    for k, rx in WK:
        if re.search(r"\b(?:%s)" % rx, t):
            return k
    return ""


def armor_bonus(txt):
    t, b = (txt or "").lower(), 0
    if re.search(r"\b(plate|full armou?r|power armou?r|exosuit)\b", t):
        b = 5
    elif re.search(r"\b(chain ?mail|mail|scale|kevlar|riot|heavy armou?r)\b", t):
        b = 3
    elif re.search(r"\b(leather|armou?r|vest|padded|robes?)\b", t):
        b = 2
    return min(6, b + (1 if re.search(r"\bshield\b", t) else 0))


# ----- units
def alive(u):
    return u["hp"] > 0 and not u.get("fled") and not u.get("dead")


def cond(u):
    if u.get("dead"):
        return "dead"
    if u.get("fled"):
        return "fled the fight"
    if u["hp"] <= 0:
        return "down, unconscious and bleeding" if not u.get("stable") else "down and unconscious"
    r = u["hp"] / u["max"]
    return "unhurt" if r > .75 else "wounded" if r > .5 else "badly hurt" if r > .25 else "barely standing"


def heft(d, mx):
    return "a devastating blow" if d >= mx * .3 else "a heavy hit" if d >= mx * .2 else "a solid hit" if d >= mx * .1 else "a light hit"


def compact_prof(p):
    return {"techs": [{k: t[k] for k in ("name", "kinds", "tags", "level")} for t in (p.get("techs") or [])[:6]], "lvl": p.get("lvl") or {}, "weak": p.get("weak") or [], "lim": (p.get("lim") or [])[:3]}


def mk_unit(uid, name, side, stats, gear, prof=None, bd=None, skills=""):
    g = ((gear or "") + " " + (skills or "")).lower()
    prof = prof or SK.parse(skills, gear)
    dv = SK.derive(prof)
    mx = max(14, 34 + 3 * md(stats["CON"]) + dv["hp"])
    bd = bd or B.blank()
    hp = max(1, round(mx * B.vitality(bd)))
    return dict(id=uid, name=name, side=side, max=mx, hp=hp, base_ac=11 + md(stats["DEX"]) + armor_bonus(g) + dv["guard"] + dv["dodge"],
                base_atk=max(md(stats["STR"]), md(stats["DEX"])) + 2, dmg=max(0, md(stats["STR"]), md(stats["DEX"])) + dv["melee"] // 2,
                magic=best(stats, ("INT", "WIS", "CHA")) + 2, die=weapon_die(g), wk=weapon_kind(g), init=md(stats["DEX"]) + dv["init"],
                special=bool(prof["lvl"].get("magic")) or bool(re.search(r"magic|spell|power|psychic|telekin|curse|hex|summon|fire|ice|lightning|blast|aura|chi|ki\b|ability|gift", g)),
                brave=bool(re.search(r"fearless|berserk|undead|golem|robot|android|unyielding|never retreat|to the death", g)),
                lethal=bool(re.search(r"assassin|murder|monster|beast|undead|demon|executioner|merciless|ruthless|bloodthirsty|predator|killer", g)),
                morale=100, tired=0, streak=0, ac=11, atk=2, pen={}, prof=compact_prof(prof), dv=dv, hits=[], stable=False, order=0)


def refresh(u, bd):
    """Recompute what wounds, sickness and tiredness do to this fighter right now."""
    p = B.penalty(bd)
    u["pen"] = p
    tired = u.get("tired", 0) // 25
    u["atk"] = u["base_atk"] - p["atk"] - p["all"] - tired
    u["ac"] = u["base_ac"] - p["guard"] - p["all"] // 2 - tired // 2
    u["spd"] = u["init"] - p["speed"]
    return u


def tech_for(u, kind, text="", act="attack"):
    """The technique a unit uses: for the player the one the action text names; for NPCs their best fit."""
    prof = u.get("prof") or {}
    if text:
        t = SK.pick(prof, text, act)
        if t:
            return t
    want = ("magic",) if kind == "magic" else ("melee", "ranged")
    ts = [t for t in prof.get("techs", []) if any(k in want for k in t["kinds"])]
    return max(ts, key=lambda t: t["level"]) if ts else None


def strike(a, t, magic=False, tech=None, tact=0, lethal=False):
    ac = t["ac"] + (4 if t.get("def") else 0)
    tb = SK.ATK[tech["level"]] if tech else 0
    power = (a["magic"] - a["pen"].get("all", 0) if magic else a["atk"]) + tb + tact + min(2, a.get("streak", 0)) - 3 - a.get("tired", 0) // 40
    r = check(power, ac)
    dmg, weak = 0, False
    if r["tier"] in ("crit", "win", "part"):
        base = (avg(2, 6) + max(0, a["magic"] - 2)) if magic else (avg(1, a["die"]) + a["dmg"])
        if tech:
            base += tech["level"] // 2
        wt = (t.get("prof") or {}).get("weak") or []
        if tech and any(g in wt for g in tech["tags"]):
            base, weak = base + base // 2, True
        base = base * 7 // 4 if r["tier"] == "crit" else base // 2 if r["tier"] == "part" else base
        dmg = max(1, base)
        before = t["hp"]
        t["hp"] = max(0, t["hp"] - dmg)
        if dmg:
            t["morale"] = max(0, t.get("morale", 100) - (22 if dmg >= t["max"] * .2 else 12 if dmg >= t["max"] * .1 else 6))
            wk = (tech["tags"][0] if tech and magic else a["wk"]) if (magic or a["wk"]) else ""
            t.setdefault("hits", []).append({"dmg": dmg, "wk": wk if wk else "", "crit": r["tier"] == "crit"})
        if t["hp"] <= 0 < before:
            over = dmg - before
            t["down"] = True
            t["dead"] = bool(lethal or a.get("lethal_now") or (r["tier"] == "crit" and over >= t["max"] * .5))
    a["streak"] = a.get("streak", 0) + 1 if r["tier"] in ("crit", "win") else 0
    a["tired"] = a.get("tired", 0) + 6
    r.update(act="power" if magic else "attack", who=a["name"], wid=a["id"], tgt=t["name"], tid=t["id"], dmg=dmg, thp=t["hp"], tmax=t["max"], ac=ac,
             tech=(tech or {}).get("name", ""), weak=weak, down=bool(t.get("down")), dead=bool(t.get("dead")), crit=r["tier"] == "crit")
    return r


def _threat(x):
    return (1 - x["hp"] / x["max"]) * 2 + (1.0 if x["side"] == "player" else .6) - (.7 if x.get("def") else 0)


def npc_turn(u, cb, evs, rnd):
    foe = u["side"] == "foe"
    opp = [x for x in cb["units"] if alive(x) and ((x["side"] in ("player", "ally")) if foe else x["side"] == "foe")]
    if not opp:
        return
    low = u["hp"] <= u["max"] * .28 or u.get("morale", 100) <= 25
    if low and not u["brave"]:
        u["fled"] = True
        evs.append({"act": "yield" if u["hp"] <= u["max"] * .2 else "flee", "who": u["name"], "wid": u["id"]})
        return
    t = max(opp, key=_threat) if foe else min(opp, key=lambda x: (x["hp"] / x["max"], x["name"]))
    has_magic = any("magic" in tt["kinds"] for tt in (u.get("prof") or {}).get("techs", []))
    use_magic = u["special"] and ((has_magic and (u["magic"] > u["atk"] or rnd % 2 == 1)) or u["magic"] > u["atk"] + 1)
    tech = tech_for(u, "magic" if use_magic else "melee")
    if u.pop("shaken", 0):
        u["atk"] -= 2
    evs.append(strike(u, t, bool(use_magic), tech, 0, u.get("lethal") and foe and t["side"] != "player"))


def begin_fight(rp, user, ust, ugear, members, foe_ids, aff, uprof=None, uskills=""):
    units = [mk_unit("user", user, "player", ust, ugear, uprof, B.get(rp, "user"), uskills)]
    for c in members:
        if B.is_dead(rp, c["id"]):
            continue
        side = "foe" if c["id"] in foe_ids else "ally" if aff.get(c["id"], 50) >= 65 else None
        if side:
            u = mk_unit(c["id"], c.get("name") or "?", side, parse_stats(c.get("stats")), c.get("combat"), None, B.get(rp, c["id"]), c.get("skills") or "")
            units.append(u)
    for i, u in enumerate(sorted(units, key=lambda u: (-u["init"], u["name"]))):
        u["order"] = i
    for u in units:
        refresh(u, B.get(rp, u["id"]))
    rp["combat"] = {"on": True, "round": 1, "units": units}
    return rp["combat"]


def end_fight(rp, turn=0, aff=None, mood=None, mercy=False):
    """The fight is over. Wounds already live in the bodies; here the fallen are settled: dead stay dead, the rest are down and need care."""
    cb = rp.get("combat") or {}
    dead = []
    for u in cb.get("units", []):
        bd = B.get(rp, u["id"])
        bd["tired"] = min(100, bd.get("tired", 0) + u.get("tired", 0))
        if u["id"] == "user":
            if u.get("down"):
                B.add_injury(bd, "beating", "ribs", 3)
            continue
        if u.get("dead"):
            B.kill(rp, u["id"], "was killed in the fight", turn, (aff or {}).get(u["id"]), (mood or {}).get(u["id"]))
            dead.append(u["id"])
        elif u.get("down") and not u.get("stable"):
            B.down(bd, False)
    rp["combat"] = None
    return dead


def fight_round(rp, user, ust, aff, act, tids, text="", uprof=None, lethal=False):
    cb = rp["combat"]
    P = next(u for u in cb["units"] if u["id"] == "user")
    for u in cb["units"]:
        refresh(u, B.get(rp, u["id"]))
    P["def"] = False
    foes = [u for u in cb["units"] if u["side"] == "foe" and alive(u)]
    tgt = next((u for u in foes if u["id"] in tids), None) or (min(foes, key=lambda u: (u["hp"] / u["max"], u["name"])) if foes else None)
    evs, end, skip = [], None, False
    me = dict(who=user, wid="user")
    uprof = uprof or P.get("prof") or {}
    tact = SK.tactics(text)
    if act in ("attack", "special") and tgt:
        tech = tech_for(P, "magic" if act == "special" else "melee", text, act)
        if act == "special" and not tech and not P.get("special"):
            evs.append(dict(me, act="other"))      # no powers to use: the move is just flailing
        else:
            evs.append(strike(P, tgt, act == "special", tech, tact, lethal))
    elif act == "defend":
        P["def"] = True
        evs.append(dict(me, act="defend"))
    elif act == "flee":
        sp = P["spd"] + SK.derive(uprof)["stealth"] // 2
        r = check(sp - 2 * len(foes) + tact, 10)
        evs.append(dict(r, me, act="flee_try", label="Flee", stat="DEX"))
        if r["tier"] in ("crit", "win"):
            end = "fled"
    elif act == "heal":
        ally = next((u for u in cb["units"] if u["side"] in ("ally", "player") and u["id"] in tids and u.get("down") and not u.get("dead")), None) \
            or next((u for u in cb["units"] if u["side"] in ("ally", "player") and u["id"] in tids and not u.get("dead")), None) \
            or next((u for u in cb["units"] if u["side"] == "ally" and u.get("down") and not u.get("dead")), None) or P
        dv = SK.derive(uprof)
        r = check(best(ust, ("WIS", "INT")) + dv["aid"] + tact, 10 + (2 if ally.get("down") else 0))
        amt = 0
        tech = tech_for(P, "heal", text, "heal")
        if r["tier"] not in ("bust", "fail"):
            amt = avg(1, 8) + max(0, best(ust, ("WIS", "INT"))) + dv["aid"]
            amt = amt * 2 if r["tier"] == "crit" else max(1, amt // 2) if r["tier"] == "part" else amt
            if ally.get("down"):
                ally["down"], ally["stable"] = False, True
                ally["hp"] = max(1, min(ally["max"], amt // 2))
            else:
                ally["hp"] = min(ally["max"], ally["hp"] + amt)
            done = B.treat(B.get(rp, ally["id"]), SK.derive(uprof)["aid"])
        evs.append(dict(r, me, act="heal", label="Aid", stat=best_name(ust, ("WIS", "INT")), tgt=ally["name"], amt=amt, thp=ally["hp"], tmax=ally["max"], tech=(tech or {}).get("name", "")))
    elif act == "persuade":
        a = sum(aff.get(u["id"], 50) for u in foes) // max(1, len(foes))
        dv = SK.derive(uprof)
        r = check(md(ust["CHA"]) + dv["social"] + tact, max(8, 12 + 2 * (len(foes) - 1) - (a - 50) // 10))
        evs.append(dict(r, me, act="talk", label="Talk them down", stat="CHA"))
        if r["tier"] in ("crit", "win"):
            end = "truce"
        elif r["tier"] == "part":
            skip = True
    elif act == "intimidate":
        dv = SK.derive(uprof)
        r = check(best(ust, ("STR", "CHA")) + max(dv["social"], dv["melee"] // 2) + tact, 12)
        evs.append(dict(r, me, act="check", label="Intimidate", stat=best_name(ust, ("STR", "CHA"))))
        if r["tier"] in ("crit", "win"):
            for u in foes:
                u["shaken"] = 1
                u["morale"] = max(0, u.get("morale", 100) - 45)
                if (u["hp"] <= u["max"] * .5 or u["morale"] <= 25) and not u["brave"]:
                    u["fled"] = True
                    evs.append({"act": "flee", "who": u["name"], "wid": u["id"]})
    elif act in LAB and act not in ("attack", "special"):
        dv = SK.derive(uprof)
        kinds = SK.ACT_KIND.get(act, ())
        r = check(best(ust, LAB[act][1]) + max([dv.get(k, 0) for k in ("stealth", "social", "wits")] or [0]) // 2 + tact, 12)
        evs.append(dict(r, me, act="check", label=LAB[act][0], stat=best_name(ust, LAB[act][1])))
    else:
        evs.append(dict(me, act="other"))
    # wounds from this round's hits land on the bodies now, so a broken arm is felt in the next exchange
    for e in evs:
        if e.get("dmg") and e["act"] in ("attack", "power"):
            tu = next((u for u in cb["units"] if u["id"] == e["tid"]), None)
            if tu and tu["hits"]:
                B.wounds_from_fight(B.get(rp, tu["id"]), [tu["hits"].pop()], tu["max"])
    if not end:
        for u in sorted([u for u in cb["units"] if u["side"] != "player" and alive(u)], key=lambda u: (u["order"])):
            if not alive(u) or P["hp"] <= 0 or not [x for x in cb["units"] if x["side"] == "foe" and alive(x)]:
                continue
            if skip and u["side"] == "foe":
                continue
            n0 = len(evs)
            npc_turn(u, cb, evs, cb["round"])
            for e in evs[n0:]:
                if e.get("dmg") and e["act"] in ("attack", "power"):
                    tu = next((x for x in cb["units"] if x["id"] == e["tid"]), None)
                    if tu and tu["hits"]:
                        B.wounds_from_fight(B.get(rp, tu["id"]), [tu["hits"].pop()], tu["max"])
    if not end:
        if P["hp"] <= 0:
            end = "defeat"
        elif not [u for u in cb["units"] if u["side"] == "foe" and alive(u)]:
            end = "victory"
    return evs, end


def ev_text(e):
    a = e["act"]
    if a in ("attack", "power"):
        r = {"crit": "a CRITICAL HIT", "win": "a clean hit", "part": "only a glancing graze", "fail": "a miss", "bust": "a clumsy fumble that leaves them open"}[e["tier"]]
        way = f" using {e['tech']}" if e.get("tech") else ""
        s = f"{e['who']} {'unleashes a power on' if a == 'power' else 'attacks'} {e['tgt']}{way}: {r}"
        if e["dmg"]:
            s += f" ({heft(e['dmg'], e['tmax'])})"
            if e.get("weak"):
                s += f"; it strikes right at {e['tgt']}'s weakness"
            if e.get("dead"):
                s += f"; {e['tgt']} is killed"
            elif e.get("down"):
                s += f"; {e['tgt']} is knocked down, unconscious and bleeding"
        return s
    if a == "defend":
        return f"{e['who']} braces and guards."
    if a == "flee_try":
        return f"{e['who']} tries to break away and escape: {TIER_TXT[e['tier']]}"
    if a == "heal":
        t = f" with {e['tech']}" if e.get("tech") else ""
        return f"{e['who']} tends to {e['tgt']}{t}: {TIER_TXT[e['tier']]}"
    if a == "talk":
        return f"{e['who']} tries to talk everyone down: {TIER_TXT[e['tier']]}"
    if a == "check":
        return f"{e['who']} tries to {e['label'].lower()}: {TIER_TXT[e['tier']]}"
    if a in ("flee", "yield"):
        return f"{e['who']} " + ("is beaten and yields, backing down." if a == "yield" else "loses their nerve and runs from the fight.")
    return f"{e['who']} does what their message says, but it has no real effect on the fight."


def ev_row(e):
    a = e["act"]
    if a in ("attack", "power"):
        res = {"crit": "Devastating", "win": "Hit", "part": "Graze", "fail": "Miss", "bust": "Fumble"}[e["tier"]]
        if e.get("dead"):
            res = "Killing blow"
        return {"who": f"{e['who']} → {e['tgt']}" + (" ✨" if a == "power" else ""), "d": (e.get("tech") or "") + (" · weakness!" if e.get("weak") else ""),
                "res": res + (f" · {heft(e['dmg'], e['tmax'])[2:]}" if e["dmg"] else ""), "tier": e["tier"],
                "ex": ("☠ dead" if e.get("dead") else "💫 down" if e.get("down") else "")}
    if a == "defend":
        return {"who": e["who"], "res": "Braces for impact", "tier": "win", "ex": "guard up until their next turn"}
    if a in ("flee", "yield"):
        return {"who": e["who"], "res": "Yields" if a == "yield" else "Flees", "tier": "win"}
    if a == "other":
        return {"who": e["who"], "res": "Acts", "tier": "win"}
    r = {"who": e["who"], "d": edge(e), "res": TIER_UI[e["tier"]], "tier": e["tier"]}
    if a == "heal":
        r["ex"] = f"{e['tgt']} " + ("steadied" if e["amt"] else "no change")
    return r


def fight_brief(cb, evs, end, started, user, byst, bodies=None):
    L = [f"[Combat - round {cb['round']}{'; a fight has just broken out' if started else ''}]", "What happened this round, in order:"]
    L += [f"{i}. {ev_text(e)}" for i, e in enumerate(evs, 1)]
    L.append("Conditions now: " + "; ".join(f"{u['name']}{' (ally)' if u['side'] == 'ally' else ' (opponent)' if u['side'] == 'foe' else ''}: {cond(u)}" for u in cb["units"]) + ".")
    for u in cb["units"]:
        bd = (bodies or {}).get(u["id"])
        d = B.describe(bd, u["id"] == "user")[:2] if bd else []
        if d:
            L.append(f"{u['name'] if u['id'] != 'user' else user}'s body: " + "; ".join(d) + ".")
    L.append("Show the fight through what each person actually does and what it costs them: pain, shock, breath, grip, footing. A wound is lasting and changes how they move and fight.")
    if byst:
        L.append("Not fighting (bystanders): " + ", ".join(byst) + ".")
    L.append({"victory": f"The fight is over: {user} won. The defeated are down, dead or have fled; the living are hurt and need care, and the dead stay dead. Wrap up the aftermath in character.",
              "defeat": f"The fight is over: {user} has been beaten and falls. Describe the aftermath from who won and what they are like (captured, spared, robbed, left behind, rescued); keep it tasteful.",
              "truce": "The fight is over: everyone stands down. They may stay wary and wounded.", "fled": f"{user} got away. The fight is over."}.get(end, ""))
    return "\n".join(l for l in L if l)
