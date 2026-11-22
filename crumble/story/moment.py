"""Read the other person's last message, so the answer fits it: no sermon for a one-word reply, no jokes for grief, a goodbye gets a goodbye.

No model call. Returns {'kinds': [...], 'words': n, 'shape': str} where shape is a one-line instruction for this reply.
"""
import re

R = [
    ("hostile", r"\b(?:shut up|idiot|stupid|hate you|screw you|liar|pathetic|useless|piss off|get lost|go to hell|moron|you suck|loser)\b"),
    ("sad", r"\b(?:sad|depress\w*|lonely|miss(?:ed|es|ing)? (?:him|her|them|you|home|my \w+)|died|passed away|funeral|cry(?:ing)?|cried|it hurts|can'?t sleep|anxious|scared|afraid|worried|stressed|exhausted|overwhelm\w*|breakup|broke up|failed|got fired|hopeless|tired of (?:it|everything|this)|not okay|i'?m (?:fine|okay)\.\.\.)\b"),
    ("goodnews", r"\b(?:got the job|i passed|promoted|i won|got accepted|engaged|pregnant|guess what|great news|good news|i did it|i made it|finally (?:got|did|finished)|best day)\b"),
    ("joke", r"(?:\blol\b|\blmao\b|\bhaha+\b|\bhehe+\b|\brofl\b|\bjk\b|\bjust kidding\b|\bkidding\b|😂|🤣|😆|\bjoking\b)"),
    ("greet", r"^\W*(?:hi|hey|hello|yo|sup|heya|hiya|morning|good (?:morning|afternoon|evening)|howdy)\b"),
    ("bye", r"\b(?:bye|goodbye|good ?night|gotta go|got to go|g2g|see you|see ya|cya|heading (?:out|off|home)|going to (?:bed|sleep)|ttyl|talk (?:to you )?later)\b"),
    ("thanks", r"\b(?:thanks|thank you|thx|ty|appreciate (?:it|you))\b"),
    ("sorry", r"\b(?:sorry|apologi[sz]e|my bad|forgive me)\b"),
    ("flirt", r"\b(?:cute|handsome|beautiful|gorgeous|pretty|hot|kiss|date|miss you|love you|babe|darling|sweetheart)\b"),
]
SHAPE = {
    "sad": "{US} seems to be hurting. Slow down. No jokes, no fixing, no advice list, no question to end on: react as a person who cares in {CH}'s own way (stay close, a few honest plain words, a small gesture).",
    "hostile": "{US} is being harsh. {CH} reacts as {CH} would (hurt, stung, defensive, cold, sharp, calm). Do not grovel and do not escalate for its own sake.",
    "goodnews": "{US} has good news. {CH} reacts for real (surprise, delight, envy, pride) before anything else.",
    "greet": "{US} is greeting {CH}. Greet back the way {CH} would at this hour and in this mood, and let the moment carry itself; do not interview them.",
    "bye": "{US} is leaving or ending the conversation. Say goodbye in {CH}'s own way, with no question and no attempt to keep them talking.",
    "thanks": "{US} is thanking {CH}. Take it the way {CH} would (brush it off, accept it, tease back) in a line or two.",
    "sorry": "{US} is apologising. {CH} answers honestly: forgive, partly forgive, or not yet, as it fits who {CH} is.",
    "flirt": "{US} is being warm or flirtatious. {CH} reacts as {CH} would at this stage of knowing them, without rushing.",
    "short": "{US}'s message is very short. Answer in kind: a line or two, not a speech.",
    "long": "{US} wrote a lot. Pick up the part that matters most to {CH} and react to that; do not answer every point.",
    "question": "{US} asked something. Answer it first, in {CH}'s own voice.",
}


def read(text):
    t = re.sub(r"\*[^*]*\*", " ", text or "")       # what they say, not what they do
    t_all = (text or "").lower()
    w = len(re.findall(r"[\w']+", t))
    low = t_all
    kinds = [k for k, rx in R if re.search(rx, low, re.I)]
    if "?" in t:
        kinds.append("question")
    if w <= 3 and w > 0:
        kinds.append("short")
    if w >= 55:
        kinds.append("long")
    order = ["sad", "hostile", "goodnews", "bye", "greet", "sorry", "thanks", "flirt", "question", "short", "long"]
    shape = next((SHAPE[k] for k in order if k in kinds), "")
    return {"kinds": kinds, "words": w, "shape": shape}
