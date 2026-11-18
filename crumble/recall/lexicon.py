"""Word lists and the tiny stemmer the memory system matches with. Data and one pure function, no model calls."""
import re

from ..config import STOPW

EXTRA_STOP = set(("when someone people being anything about very really feel feeling has get gets makes make into from them they "
                  "their there then than will would could should only also much more most some such what which while where who "
                  "whom whose been were does done doing yeah yes okay ok well oh hey hello thanks thank sure maybe just got "
                  "going gonna wanna think know see say said tell told one two want need let lets back here now still even "
                  "ever never again too out off over our ours mine yours him her hers its it's i'm you're don't can't "
                  "remember remembered remembers remembering forget forgot forgotten").split())


IRREGULAR = {"broke": "break", "broken": "break", "took": "take", "taken": "take", "gave": "give", "given": "give", "bought": "buy",
             "met": "meet", "wrote": "write", "written": "write", "ate": "eat", "eaten": "eat", "drank": "drink", "drunk": "drink",
             "fell": "fall", "fallen": "fall", "lost": "lose", "found": "find", "ran": "run", "went": "go", "gone": "go", "saw": "see",
             "seen": "see", "knew": "know", "known": "know", "felt": "feel", "kept": "keep", "sold": "sell",
             "stole": "steal", "stolen": "steal", "swore": "swear", "sworn": "swear", "began": "begin", "begun": "begin", "drove": "drive",
             "children": "child", "mice": "mouse", "men": "man", "women": "woman"}


def stem(w):
    """Crude but consistent: kissed/kisses/kiss, hugging/hugged/hug, gifts/gift, promises/promised/promise all agree."""
    w = w.lower().strip("'")
    if w in IRREGULAR:
        w = IRREGULAR[w]
    if w.endswith("'s"):
        w = w[:-2]
    if len(w) <= 3:
        return w
    if w.endswith("ies") or w.endswith("ied"):
        w = w[:-3] + "y"
    elif w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("es") and len(w) > 4 and (w[-3] in "sxz" or w[-4:-2] in ("ch", "sh")):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        w = w[:-1]
    for suf in ("ingly", "edly", "ing", "ed", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "lsz":
                w = w[:-1]
            break
    return w[:-1] if len(w) > 3 and w.endswith("e") else w


WORD = re.compile(r"[a-z][a-z']{2,}|\d{1,4}(?:st|nd|rd|th)?\b")


def terms(text):
    """A text -> list of content stems (stop words dropped, order kept, duplicates kept for weighting)."""
    return [re.sub(r"(?<=\d)(?:st|nd|rd|th)$", "", w) if w[0].isdigit() else stem(w)
            for w in WORD.findall((text or "").lower().replace("’", "'"))
            if w not in STOPW and w not in EXTRA_STOP and w not in ("{{user}}", "{{char}}", "user", "char")]


def _bag(words):
    return frozenset(stem(w) for w in words.split())


# category -> (how memorable such a moment usually is, the words that signal it).  Also the bridge that lets
# "what did you get me for my birthday?" find "Sam gave her a necklace": both touch the 'gift' category.
EVENTS = {
    "gift": (.70, "gift present gave give given giving necklace ring bracelet flowers bouquet surprise bought wrapped card keepsake"),
    "birthday": (.70, "birthday cake candle candles party celebrate celebrated anniversary"),
    "promise": (.80, "promise promised swear swore vow pledge oath guarantee"),
    "secret": (.75, "secret secrets confess confessed confession admit admitted revealed discovered hidden truth lied lie caught"),
    "romance": (.80, "kiss kissed love loved crush date dating hug hugged cuddle cuddled embrace romantic flirt flirted blush held hand"),
    "conflict": (.75, "fight fought argue argued argument yell yelled angry furious slap slapped punch punched betray betrayed insult insulted shout shouted"),
    "apology": (.70, "sorry apologize apologise apologized forgive forgave forgiveness regret"),
    "loss": (.85, "died death dead funeral lost grief mourn mourning passed buried goodbye"),
    "achievement": (.65, "won win passed promotion graduate graduated hired accomplished finished succeeded"),
    "milestone": (.80, "first ever married engaged proposal proposed moved together officially"),
    "trust": (.70, "trust trusted confide confided rely depend vulnerable opened"),
    "meeting": (.55, "met meet introduce introduced stranger arrived"),
    "trip": (.50, "trip travel flight journey visited vacation holiday"),
    "danger": (.80, "danger saved rescue rescued injured wounded attack attacked hospital hurt bleeding"),
}
EVENT_BAGS = {k: (imp, _bag(w)) for k, (imp, w) in EVENTS.items()}


def categories(text):
    """Event categories a text touches."""
    t = set(terms(text))
    return [k for k, (_, bag) in EVENT_BAGS.items() if t & bag]


# emotion group -> (valence, words).  Used to match emotional memories and to colour recall by the current mood.
EMOTIONS = {
    "joy": (.8, "happy joyful joy delighted thrilled excited glad cheerful elated amused proud grateful relieved hopeful content playful smug confident"),
    "love": (.9, "loved adored affectionate fond tender cherished touched smitten warm"),
    "sad": (-.7, "sad heartbroken hurt lonely grief crushed disappointed miserable devastated tearful cry cried lonely guilty"),
    "anger": (-.8, "angry furious annoyed irritated outraged livid resentful bitter betrayed frustrated jealous disgusted"),
    "fear": (-.7, "afraid scared terrified anxious nervous worried frightened panic uneasy fearful"),
    "shame": (-.6, "embarrassed ashamed humiliated flustered awkward mortified shy"),
    "calm": (.4, "calm relaxed safe peaceful comforted secure relaxed"),
    "surprise": (0.0, "surprised shocked stunned startled astonished confused"),
}
EMO_BAGS = {k: (v, _bag(w)) for k, (v, w) in EMOTIONS.items()}
STRONG_EXTRA = _bag("touched grateful excited hurt jealous flustered heartbroken")


def is_strong(word):
    """A feeling intense enough to be worth remembering (anger, love, joy, sadness, fear, shame - not calm or mild)."""
    g, v = emotion_group(word)
    return bool(g and abs(v) >= .6) or stem((word or "").lower()) in STRONG_EXTRA


def emotion_group(word):
    """-> (group, valence) for a mood/feeling word, or (None, 0.0)."""
    s = stem((word or "").lower())
    for k, (v, bag) in EMO_BAGS.items():
        if s in bag:
            return k, v
    return None, 0.0


def emotions_in(text):
    """[(group, valence)] mentioned in a text."""
    t = set(terms(text))
    return [(k, v) for k, (v, bag) in EMO_BAGS.items() if t & bag]


# cues that the person is reaching back into the past: widen the search and favour events
REACH_BACK = re.compile(r"\b(?:remember|remind(?:ed)? me|last time|that time|back when|earlier|before|used to|ago|when (?:i|we|you)|"
                        r"what happened|did you (?:forget|know)|you promised|you said|i told you|told you)\b", re.I)
EXPLICIT_KEEP = re.compile(r"\b(?:remember (?:this|that|it|me)|don'?t forget|never forget|keep (?:this|that) in mind|"
                           r"i (?:want|need) you to remember|write (?:this|that) down)\b", re.I)

# positive / negative words for the plain-language polarity of a fact, e.g. "likes coffee" vs "hates coffee"
LIKE_WORDS = ("likes", "loves", "enjoys", "prefers", "adores", "is fond of")
DISLIKE_WORDS = ("dislikes", "hates", "can't stand", "despises", "doesn't like", "does not like", "is tired of", "avoids")
