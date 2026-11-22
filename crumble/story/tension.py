"""Conflict, without a fight engine.

There are no rounds, no hit points and no keyword that starts a brawl. Conflict is story: it grows out of who the people are and what is at stake,
it escalates through words, posture and warnings, and people do what real people do (argue, stonewall, back off, leave, call for help, freeze).
Violence happens only when the story and the characters truly lead there; then it is fast, messy and has consequences that last (wounds are read
from the narration and kept by the body module; relationships, trust and memory change). The character's own fighting skills (the sheet's
"fighting style" field) and the other person's skills only enter the prompt once a conflict is actually brewing.

    level(texts)               0 calm, 1 tension (hostile words, a threat), 2 danger (weapons, blows, a life at risk)
    standing(name, user)       one short rule that is always present
    block(c, level, user, uskills)   the full guidance once there is tension
"""
import re

HOT = re.compile(r"(?i)\b(?:shut up|idiot|stupid|hate you|liar|pathetic|screw you|how dare|get out|back off|stay away|i'?ll make you|you'?ll regret|or else|threaten\w*|furious|enraged|storms? out|slams? the door|glares?|snarls?|sneers?)\b")
DANGER = re.compile(r"(?i)\b(?:kill\w*|stab\w*|shoot\w*|shot|punch\w*|slap\w*|strangl\w*|blade|knife|gun|pistol|sword|weapon|blood\w*|bleed\w*|attack\w*|ambush\w*|hostage|choke\w*|drags?|swings? at|lunges?|tackles?|fires? at|draws? (?:a|his|her|their|the) (?:sword|blade|gun|knife|weapon))\b")


def level(texts):
    t = [re.sub(r"<think>.*?(?:</think>|$)", "", x or "", flags=re.S) for x in texts[-4:]]
    d = sum(len(DANGER.findall(x)) for x in t)
    h = sum(len(HOT.findall(x)) for x in t)
    return 2 if d >= 2 or (d >= 1 and h >= 1) else 1 if (d or h >= 2) else 0


def standing(name, user):
    return (f"Conflict and danger are story, not a game: no one picks a fight out of nowhere. {name} gets angry, scared, stubborn or defensive for reasons, "
            f"and mostly shows it with words, silence, posture and leaving. Never start violence just because a word like 'fight' or 'hit' appeared.")


def block(c, lvl, name, user, uskills="", ugear=""):
    if lvl <= 0:
        return ""
    L = [f"[Conflict - this is real tension, not a minigame]"]
    L.append(f"What {name} does now comes from who {name} is: temper, fears, loyalties, pride, what is at stake, who is watching and where this is happening. "
             f"People rarely go straight to violence: they warn, posture, argue, stonewall, back away, call for help, freeze, bargain, or leave. Let {name} do what fits, and let it escalate or cool as a person would.")
    if lvl >= 2:
        L.append(f"Danger is real here. If violence happens, write it as story, not as rounds: quick, confused and physical, with fear, adrenaline, pain and shock; "
                 f"let the outcome follow from skill, weapons, surprise, the place and everyone's condition (an exhausted, wounded or outnumbered person does worse), not from a script. "
                 f"{user} acts for themselves and {name} reacts as a person would: they may be hurt, may hurt back, may flee, yield or freeze. "
                 f"A wound is lasting and changes how someone moves and speaks; a death is final; witnesses react; trust, fear and memory change afterwards. Resolve the clash within a few exchanges and show the aftermath instead of dragging it on.")
    fs = str(c.get("combat") or "").strip()
    if fs:
        L.append(f"{name}'s fighting skills, gear or powers (use them only if it truly comes to that): {fs[:300]}")
    sk = str(c.get("skills") or "").strip()
    if sk and lvl >= 2:
        L.append(f"{name}'s other abilities: {sk[:240]}")
    if lvl >= 2 and (uskills.strip() or ugear.strip()):
        L.append(f"What {name} has seen {user} do or carry: {(uskills.strip() + ' ' + ugear.strip()).strip()[:300]}. Use these real abilities and limits when describing what {user} does.")
    L.append("Never mention game mechanics, hit points, dice, rounds or numbers.")
    return "\n".join(L)
