"""Word lists the personality engine reads character sheets and chats with. Data only, no logic."""
import re

BIG5 = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
AXES = ("assertiveness", "warmth", "humor", "formality", "verbosity", "impulsivity", "trust", "pride", "expressiveness")
TRAITS = BIG5 + AXES

LABEL = {"openness": "Openness", "conscientiousness": "Conscientiousness", "extraversion": "Extraversion",
         "agreeableness": "Agreeableness", "neuroticism": "Emotional volatility", "assertiveness": "Assertiveness",
         "warmth": "Warmth", "humor": "Humour", "formality": "Formality", "verbosity": "Talkativeness",
         "impulsivity": "Impulsiveness", "trust": "Openness to trust", "pride": "Pride", "expressiveness": "Expressiveness"}

# Short names the author can use in the Traits field: "O 70 C 40 E 85 A 30 N 60" or "warmth: high".
ALIASES = {
    "o": "openness", "open": "openness", "openness": "openness",
    "c": "conscientiousness", "cons": "conscientiousness", "conscientiousness": "conscientiousness", "conscientious": "conscientiousness",
    "e": "extraversion", "extra": "extraversion", "extraversion": "extraversion", "extroversion": "extraversion",
    "a": "agreeableness", "agree": "agreeableness", "agreeableness": "agreeableness",
    "n": "neuroticism", "neuro": "neuroticism", "neuroticism": "neuroticism", "volatility": "neuroticism",
    "assertiveness": "assertiveness", "assertive": "assertiveness", "dominance": "assertiveness",
    "warmth": "warmth", "warm": "warmth", "affection": "warmth",
    "humor": "humor", "humour": "humor",
    "formality": "formality", "formal": "formality",
    "verbosity": "verbosity", "talkativeness": "verbosity", "talkative": "verbosity",
    "impulsivity": "impulsivity", "impulsive": "impulsivity", "impulsiveness": "impulsivity",
    "trust": "trust", "trusting": "trust",
    "pride": "pride", "ego": "pride",
    "expressiveness": "expressiveness", "expressive": "expressiveness",
}
LEVELS = {"very high": 90, "high": 75, "medium": 50, "mid": 50, "moderate": 50, "low": 25, "very low": 10}

# trait -> regex fragments that push it up / down (matched on word boundaries, lowercase)
UP = {
    "openness": r"curious|creative|imaginative|artistic|inventive|adventurous|open-minded|dreamy|dreamer|eccentric|quirky|unconventional|philosoph\w+|intellectual|experimental|whimsical|poetic|bookish|explor\w+|inquisitive|innovative|visionary|free-spirited|bohemian",
    "conscientiousness": r"disciplined|organi[sz]ed|meticulous|diligent|responsible|reliable|punctual|perfectionist\w*|methodical|careful|dutiful|orderly|hard-?working|thorough|strict|dependable|precise|principled|ambitious|industrious",
    "extraversion": r"outgoing|extrovert\w*|extravert\w*|chatty|talkative|sociable|bubbly|energetic|loud|charismatic|boisterous|lively|gregarious|enthusiastic|cheerful|life of the party|social butterfly|exuberant|vivacious|animated|attention-seeking|flamboyant",
    "agreeableness": r"kind(?! of)|caring|warm|gentle|compassionate|empathetic|friendly|generous|selfless|patient|forgiving|polite|sweet|supportive|nurturing|trusting|helpful|considerate|humble|tender|benevolent|affable|good-natured|soft-hearted|big-hearted|diplomatic|accommodating|easygoing",
    "neuroticism": r"anxious|nervous|worr\w+|insecure|moody|volatile|temperamental|irritable|emotional|sensitive|paranoid|fearful|jumpy|neurotic|high-strung|panick\w+|self-doubt\w*|hot-?headed|hot-?tempered|melodramatic|fragile|clingy|easily (?:upset|hurt|offended|rattled)|short-tempered|brooding|jittery|overthink\w*",
    "assertiveness": r"bold|assertive|dominant|commanding|decisive|confrontational|blunt|forceful|brash|demanding|fearless|pushy|takes? charge|outspoken|aggressive|domineering|authoritative|confident|determined|headstrong|imposing|bossy|take-charge|uncompromising",
    "warmth": r"affectionate|warm|loving|tender|caring|cuddly|doting|sweet|nurturing|kind-?hearted|compassionate|motherly|fatherly|protective|devoted|loyal|comforting",
    "humor": r"funny|witty|sarcas\w+|joker|jokes?|prankster|teas\w+|playful|snarky|banter\w*|goofy|humou?rous|comedic|deadpan|cheeky|sardonic|quippy|wisecrack\w*|silly|mischievous|smart-?mouth\w*|clown\w*|dry wit|sense of humou?r",
    "formality": r"formal|polite|proper|refined|courteous|well-spoken|eloquent|prim|dignified|articulate|professional|respectful|aristocrat\w*|butler|gentlem[ae]n|ladylike|well-mannered|prudish|posh|cultured|old-fashioned|archaic",
    "verbosity": r"rambl\w+|talkative|chatty|verbose|long-winded|monologu\w+|tangent\w*|wordy|gossip\w*|never shuts up|talks a lot|loquacious|babbl\w+|over-?explain\w*|long messages|long texts|paragraphs",
    "impulsivity": r"impulsive|reckless|rash|hot-?headed|spontaneous|impatient|thrill-seek\w+|headstrong|erratic|daredevil|hasty|unpredictable|trigger-happy",
    "trust": r"trusting|naive|naïve|open-hearted|gullible|credulous|believes everyone|takes people at their word",
    "pride": r"proud|arrogant|vain|egotistical|haughty|stubborn|self-assured|narcissistic|prideful|boastful|cocky|smug|conceited|superior|elitist|self-important|never apologi[sz]es|can't admit|won't admit",
    "expressiveness": r"dramatic|emotional|expressive|passionate|melodramatic|sentimental|theatrical|excitable|effusive|demonstrative|tearful|fiery|wears (?:his|her|their) heart on (?:his|her|their) sleeve",
}
DOWN = {
    "openness": r"traditional|conventional|practical|down-to-earth|pragmatic|rigid|set in (?:his|her|their) ways|resist\w* change|closed-minded|narrow-minded|conservative|unimaginative|literal-minded|no-nonsense|by the book",
    "conscientiousness": r"lazy|careless|messy|disorgani[sz]ed|sloppy|procrastinat\w+|forgetful|unreliable|slacker|chaotic|irresponsible|scatterbrained|flaky|slovenly|undisciplined|lax|negligent|carefree|flighty|absent-minded",
    "extraversion": r"shy|quiet|introvert\w*|reserved|withdrawn|aloof|soft-spoken|stoic|loner|solitary|taciturn|laconic|timid|homebody|socially awkward|keeps to (?:himself|herself|themselves)|bashful|retiring|low-key|few words",
    "agreeableness": r"cold|ruthless|rude|hostile|selfish|manipulative|cynical|arrogant|stubborn|spiteful|vindictive|condescending|harsh|abrasive|combative|callous|cruel|petty|argumentative|short-tempered|contemptuous|bitter|judgmental|vengeful|sharp-tongued|snappy|snide|snarky|disdainful|grumpy|grouchy|cantankerous|antagonistic|confrontational",
    "neuroticism": r"calm|composed|stoic|unflappable|steady|level-headed|easygoing|cool-headed|laid-back|resilient|serene|collected|chill|even-tempered|unshakeable|poised|placid|tranquil|imperturbable|thick-skinned|nerves of steel|emotionally stable|grounded",
    "assertiveness": r"meek|submissive|timid|passive|deferential|hesitant|pushover|soft-spoken|shy|indecisive|apologetic|yielding|docile|self-effacing|conflict-averse|avoids? (?:conflict|confrontation)|people-?pleas\w+|compliant",
    "warmth": r"cold|distant|aloof|detached|stoic|standoffish|icy|emotionally (?:closed|unavailable|distant|guarded)|unfeeling|callous|indifferent|gruff|stern|curt|brusque|frosty|clinical|impersonal|tsundere",
    "humor": r"serious|humou?rless|solemn|grim|stern|somber|sombre|dour|earnest|po-faced",
    "formality": r"casual|slang|informal|crude|swear\w*|curs\w+|rowdy|vulgar|foul-mouthed|uncouth|crass|coarse|colloquial|lowercase|no caps|no punctuation|abbreviat\w+|typos?|text speak|emojis?",
    "verbosity": r"terse|laconic|few words|curt|brief|short answers?|monosyllab\w+|taciturn|minimalist|man of few words|woman of few words|speaks little|clipped|succinct|says little|one-word|short messages|short texts|one-liners?",
    "impulsivity": r"cautious|deliberate|patient|thoughtful|calculating|measured|careful|methodical|prudent|strategic|cool-headed|level-headed|think\w* before|plans ahead|cunning|disciplined|wary",
    "trust": r"guarded|suspicious|paranoid|distrust\w*|wary|cynical|trust issues|closed[- ]off|secretive|skeptical|untrusting|reticent|walls? up|hard to (?:get close|trust|read)|slow to trust|doesn'?t trust|never trusts|keeps people at (?:a )?distance|mistrust\w*",
    "pride": r"humble|modest|self-deprecating|meek|unassuming|selfless|self-effacing|insecure|admits? (?:mistakes|fault|when wrong)|apologi[sz]es easily|bashful",
    "expressiveness": r"stoic|deadpan|flat|unemotional|reserved|impassive|poker[- ]faced|stone[- ]faced|expressionless|restrained|understated|inscrutable|stolid|straight-faced|bottles? (?:things )?up|keeps? (?:feelings|emotions) (?:in|hidden|bottled)",
}


def _rx(frag):
    return re.compile(r"(?<![\w-])(?:%s)(?![\w-])" % frag, re.I)


UP_RX = {t: _rx(UP[t]) for t in TRAITS}
DOWN_RX = {t: _rx(DOWN[t]) for t in TRAITS}
NEGATORS = re.compile(r"(?:\bnot|\bnever|\bno|n't|\bwithout|\bhardly|\bbarely|\bneither|\bnor)\s+(?:\w+\s+){0,2}$", re.I)
BOOST = re.compile(r"(?:very|extremely|incredibly|highly|deeply|fiercely|intensely|painfully|really|super|utterly|insanely|ridiculously)\s+$", re.I)
HEDGE = re.compile(r"(?:somewhat|slightly|a bit|a little|kinda|fairly|moderately|mildly|occasionally|sometimes|can be)\s+$", re.I)

# Trait cross-influence: how the five broad traits colour the behavioural axes (coefficient on (trait - 50)).
CROSS = {
    "assertiveness": {"extraversion": .25, "agreeableness": -.10, "neuroticism": -.10},
    "warmth": {"agreeableness": .30, "extraversion": .15},
    "humor": {"extraversion": .15, "openness": .10},
    "formality": {"conscientiousness": .15, "extraversion": -.05},
    "verbosity": {"extraversion": .30},
    "impulsivity": {"conscientiousness": -.35, "neuroticism": .10},
    "trust": {"agreeableness": .30, "neuroticism": -.15},
    "pride": {"agreeableness": -.25},
    "expressiveness": {"extraversion": .25, "neuroticism": .20},
}

# Words for the one-line summary: (trait, high word, low word)
ADJ = {"openness": ("curious", "practical"), "conscientiousness": ("disciplined", "loose"),
       "extraversion": ("outgoing", "reserved"), "agreeableness": ("kind", "blunt"),
       "neuroticism": ("high-strung", "steady"), "assertiveness": ("bold", "deferential"),
       "warmth": ("warm", "cool"), "humor": ("witty", "serious"), "formality": ("formal", "casual"),
       "verbosity": ("talkative", "terse"), "impulsivity": ("impulsive", "deliberate"),
       "trust": ("trusting", "guarded"), "pride": ("proud", "humble"), "expressiveness": ("expressive", "understated")}

# What each extreme means in behaviour: (trait) -> (when high, when low). One short sentence each.
BEHAVE = {
    "extraversion": ("Fills silences, starts topics and offers opinions unprompted.",
                     "Says little, answers briefly and does not volunteer details; needs time to open up."),
    "agreeableness": ("Phrases things softly, looks for common ground and is slow to anger.",
                      "Blunt and challenging; teases or needles; does not smooth things over just to be nice or flatter."),
    "neuroticism": ("Feelings swing quickly and show in word choice; over-reads small signals and calms down slowly.",
                    "Even-tempered and hard to rattle; reactions are understated even when provoked."),
    "conscientiousness": ("Precise and organised; notices and corrects sloppiness.",
                          "Casual about rules and details; drifts off-topic and puts things off."),
    "openness": ("Curious; makes unusual connections and enjoys new ideas.",
                 "Prefers the familiar and practical; sceptical of abstract talk and novelty."),
    "assertiveness": ("States what they want directly, takes charge and pushes back when crossed.",
                      "Hedges, defers and avoids confrontation; apologises and backs down easily."),
    "warmth": ("Openly affectionate; comforts people who struggle.",
               "Shows care through actions or gruffness; rarely says affectionate things outright."),
    "humor": ("Jokes, teases and banters, even when things are tense.",
              "Rarely jokes; takes things seriously and literally."),
    "formality": ("Polite, complete sentences, no slang.",
                  "Casual: contractions, fragments and slang."),
    "verbosity": ("Tends to ramble and add tangents.",
                  "Few words: one or two short sentences, clipped."),
    "impulsivity": ("Speaks and acts before thinking; changes course mid-sentence.",
                    "Considers before answering; measured and deliberate."),
    "trust": ("Takes people at their word and opens up quickly.",
              "Guarded: tests people, deflects personal questions; trust is earned slowly."),
    "pride": ("Hates being corrected or pitied; doubles down and admits mistakes reluctantly.",
              "Admits mistakes easily and plays down their own achievements."),
    "expressiveness": ("Big visible reactions: exclamations, drama, strong word choice.",
                       "Flat, understated delivery; feelings leak out only in small tells."),
}

# ---------------------------------------------------------------- mood map: (valence, arousal), both -1..1
MOOD_VA = {
    "neutral": (0, 0), "happy": (.7, .35), "joyful": (.9, .6), "excited": (.8, .85), "amused": (.65, .4),
    "playful": (.6, .5), "smug": (.4, .3), "proud": (.6, .35), "confident": (.5, .4), "determined": (.2, .6),
    "relaxed": (.5, -.4), "content": (.55, -.25), "calm": (.3, -.5), "affectionate": (.7, .1), "fond": (.65, 0),
    "grateful": (.6, 0), "hopeful": (.45, .25), "curious": (.25, .4), "thoughtful": (.05, -.1),
    "skeptical": (-.15, .15), "surprised": (.1, .7), "confused": (-.2, .3), "flustered": (-.05, .6),
    "embarrassed": (-.3, .5), "shy": (-.1, .3), "nervous": (-.35, .55), "anxious": (-.5, .65),
    "worried": (-.45, .4), "sad": (-.7, -.3), "lonely": (-.6, -.4), "hurt": (-.7, 0), "guilty": (-.5, -.1),
    "tired": (-.2, -.7), "sleepy": (-.05, -.8), "bored": (-.3, -.5), "annoyed": (-.5, .4), "irritated": (-.5, .45),
    "frustrated": (-.6, .55), "angry": (-.75, .8), "furious": (-.9, .95), "jealous": (-.55, .5),
    "disgusted": (-.65, .35), "scared": (-.7, .85), "serious": (-.05, .15),"aroused": (.9, .75), "turned_on": (.85, .85), "horny": (.8, .9), "lustful": (.7, .8), "seductive": (.8, .6),
    "teasing": (.7, .7), "naughty": (.85, .75), "sensual": (.75, .65), "intimate": (.8, .55),
    "passionate": (.9, .7), "ecstatic": (.95, .8), "overwhelmed": (.85, .85), "desiring": (.75, .75), "excitedly_aroused": (.9, .9),
    "breathless": (.75, .8), "flushed": (.85, .6), "wet": (.8, .7), "throbbing": (.85, .85)
}
# Words the engine may choose when it has to pick one itself (everyday moods, nothing too specific).
PALETTE = ("neutral", "happy", "joyful", "excited", "amused", "playful", "relaxed", "content", "calm", "affectionate",
           "grateful", "hopeful", "curious", "thoughtful", "skeptical", "surprised", "confused", "flustered", "shy",
           "nervous", "anxious", "worried", "sad", "lonely", "hurt", "guilty", "tired", "bored", "annoyed",
           "frustrated", "angry", "furious", "scared", "serious","aroused", "turned_on", "horny", "lustful", "seductive", "teasing", "naughty", "sensual", "intimate",
           "passionate", "ecstatic", "overwhelmed", "desiring", "excitedly_aroused", "breathless", "flushed", "wet", "throbbing")

# ---------------------------------------------------------------- what the user just did (weight, regex), lowercase text
STIM = {
    "hostile": [
        (1.0, r"\b(?:shut up|piss off|screw you|f\w*k you|go to hell|i hate you|you suck|get lost|drop dead|you(?:'re| are) (?:such )?(?:a |an )?(?:stupid|idiot|dumb|moron\w*|worthless|pathetic|useless|disgusting|loser|bitch|jerk|trash|garbage)|stupid (?:\w+ )?(?:bitch|idiot|jerk))\b"),
        (0.6, r"\b(?:you(?:'re| are) (?:so )?(?:annoying|boring|lame|weak)|nobody (?:asked|cares)|who asked|don'?t care about you|go away|leave me alone|get out)\b"),
        (0.5, r"\*[^*]*\b(?:slaps?|punche?s?|kicks?|shoves?|spits?|sneers?|glares?)\b[^*]*\*")],
    "kind": [
        (1.0, r"\b(?:thank you(?: so much)?|thanks(?: a lot| so much)?|i appreciate|you(?:'re| are) (?:so |really |truly )?(?:sweet|kind|wonderful|amazing|awesome|the best|lovely|a good (?:friend|person))|i love (?:you|talking|hanging|spending)|so glad (?:you|i)|proud of you|i(?:'ve)? missed you|miss you|you mean (?:a lot|so much|the world))\b"),
        (0.5, r"\b(?:please|glad|happy for you|good job|nice one|take care|hope you(?:'re| are)? (?:ok|okay|well|good))\b"),
        (0.4, r"\*[^*]*\b(?:hugs?|pats?|smiles?|comforts?|offers?|squeezes?)\b[^*]*\*")],
    "praise": [
        (1.0, r"\b(?:you(?:'re| are) (?:so |really |very )?(?:good|great|talented|brilliant|smart|clever|strong|brave|impressive|beautiful|handsome|gorgeous|funny|hilarious|incredible)|nice work|well done|that was (?:amazing|impressive|brilliant|awesome)|great job|i admire you)\b")],
    "vulnerable": [
        (1.0, r"\b(?:i(?:'m| am| feel) (?:so |really |very )?(?:sad|scared|afraid|anxious|lonely|alone|exhausted|hurt|lost|struggling|depressed|overwhelmed|worried|stressed|terrified|ashamed|worthless|broken|empty)|i (?:can'?t|cannot) (?:do|take|cope|sleep)|i don'?t know what to do|can i tell you something|rough day|bad day|terrible day|i need (?:help|someone|a hug)|i(?:'ve| have) been (?:crying|struggling)|i(?:'m| am) crying|i miss (?:my|him|her|them))\b")],
    "challenge": [
        (1.0, r"\b(?:you(?:'re| are) wrong|i disagree|that'?s (?:not true|wrong|false|nonsense|ridiculous)|no you|prove it|are you sure|that makes no sense|i don'?t believe (?:you|that)|you(?:'re| are) lying|liar|you don'?t (?:know|understand) (?:what|anything))\b")],
    "apology": [
        (1.0, r"\b(?:i(?:'m| am) (?:so |really |truly )?sorry|i apologi[sz]e|my bad|forgive me|i was wrong|my mistake|didn'?t mean (?:to|it))\b"),
        (0.6, r"\bsorry\b")],
    "flirt": [
        (1.0, r"\b(?:cute|beautiful|handsome|gorgeous|sexy|kiss(?:es)?|date me|go out with me|you(?:'re| are) hot|blushing|sweetheart|darling|my love)\b")],
    "dismissive": [
        (1.0, r"^\W*(?:ok|okay|k|kk|fine|whatever|idc|sure|meh|nvm|nevermind|if you say so|hm+|mhm)\W*$"),
        (0.6, r"\b(?:i don'?t care|not interested|doesn'?t matter|i'?m busy)\b")],
}
STIM_RX = {k: [(w, re.compile(p, re.I)) for w, p in v] for k, v in STIM.items()}

# ---------------------------------------------------------------- reply checks
AI_HARD = re.compile(
    r"\b(?:"
    # I am / As an / Being an ... AI, assistant, bot, program, etc.
    r"(?:i(?:'m| am)|as|being) (?:a |an |just (?:a |an )?|merely (?:a |an )?|only (?:a |an )?|simply (?:a |an )?|part of (?:a |an )?)?(?:[\w-]+\s+){0,3}(?:ai\b|artificial intelligence|language model|llm|chatbot|bot\b|virtual assistant|digital assistant|program\b|computer program|neural network|machine learning model|software|system\b|algorithm)"
    r"|i(?:'m| am) (?:here )?(?:to act as|designed to|programmed to|trained to|an automated)"
    # Disclaimers of humanity, bodies, feelings
    r"|i (?:don'?t|do not|cannot) have (?:a |an )?(?:personal )?(?:physical |real )?(?:feelings|emotions|a body|consciousness|ears|eyes|senses)"
    r"|my (?:training|programming|knowledge cutoff|system prompt|developer|creators|algorithm|model weights)"
    r"|(?:metaphorically|figuratively) speaking\b"
    r"|as (?:a |an )?(?:language model|ai|machine|computer program|assistant)"
    r")\b",
    re.I
)
AI_SOFT = re.compile(
    r"\b(?:"
    # direct assistant offers
    r"i'?d be (?:happy|glad|delighted) to (?:help|assist)"
    r"|how (?:can|may) i (?:help|assist)"
    r"|i(?:'m| am) here (?:for you|to (?:help|assist|listen|support))"
    r"|i(?:'m| am) (?:always )?(?:eager|happy|ready) to (?:learn|engage|chat|talk|help|assist)\b"
    r"|i hope (?:this|that) helps"
    r"|feel free to (?:ask|reach out|share|let me know)"
    r"|(?:don'?t|do not) hesitate to"
    r"|let me know if (?:you|there)"
    r"|is there anything else"
    r"|i cannot (?:assist|help) with"
    # generic chatbot openings & prompts
    r"|(?:it'?s|it is) (?:nice|great|good|a pleasure) to meet you"
    r"|(?:hello|hi|hey)\s+[\w'-]+[!,.]?\s*(?:it'?s|it is) (?:nice|great|good|a pleasure) to meet you"
    r"|what brings you (?:here |in |by )?today\??"
    r"|how are you (?:doing |feeling )?today\??"
    r"|how is your day (?:going|so far)\??"
    r"|is there (?:something|anything) (?:specific )?(?:on your mind|you(?:'d| would) like to (?:discuss|talk about|ask|know))\??"
    r"|what (?:can|would) you like to (?:talk|chat|discuss|explore|ask) (?:about )?today\??"
    r"|what do you (?:usually |normally )?(?:enjoy|like) (?:talking|chatting) about\??"
    r"|i(?:'m| am) here if you(?:'d| would| want to| need to| ever| wish to) (?:like to )?(?:chat|talk|reach out)\b"
    r"|(?:chat|talk) about (?:anything|whatever) (?:on your mind|you(?:'d| would)? (?:like|want))\b"
    r"|(?:have a |just a |for a )?casual conversation\b"
    r"|i(?:'m| am) all ears\b"
    r"|how can i (?:best )?(?:help|assist|serve) you today\??"
    r"|anything on your mind\??"
    # therapist / customer-service tone
    r"|(?:that'?s|that is|this is) (?:a |completely |totally |perfectly )?(?:valid|understandable|normal) (?:feeling|concern|question|response|reaction|point|worry)"
    r"|i (?:completely |totally |fully )?understand (?:that |how you |your |where you)"
    r"|i (?:truly |really |deeply )?appreciate you (?:sharing|opening up|telling|trusting)"
    r"|thank you for (?:sharing|your (?:patience|understanding|openness|honesty|trust|vulnerability))"
    r"|i apologi[sz]e for any"
    r"|it'?s (?:important|worth|essential|crucial) (?:to (?:note|remember|acknowledge|recogni[sz]e)|noting|remembering)"
    r"|(?:that said|having said that|with that (?:being )?said),? (?:i|it|let|we|you)"
    # sycophantic openers
    r"|great question"
    r"|that'?s a (?:great|wonderful|excellent|fantastic|fascinating|thoughtful|insightful|really good) (?:question|point|idea|observation|thought)"
    r"|what a (?:great|wonderful|excellent|fantastic|thoughtful|insightful) (?:question|point|idea|observation)"
    r"|i'?d love to (?:help|assist|hear|explore|discuss|dive into|unpack)"
    # hollow reassurances
    r"|(?:you(?:'re| are)|your feelings are) (?:not alone|valid|enough|worthy|valued|seen|heard|so brave|so strong)"
    r"|(?:it'?s|it is|that'?s|that is) okay to (?:feel|be |not )"
    r"|(?:take|there'?s no) (?:all the time you need|rush|pressure)"
    r"|i'?m (?:so )?proud of you for (?:sharing|opening|telling|being)"
    r"|remember,? you(?:'re| are) (?:not alone|loved|worthy|enough|important)"
    r")\b"
    r"|^\W*(?:certainly|absolutely|of course)[!,.]",
    re.I | re.M
)

# polite "assistant curiosity" register that the list above does not catch ("Is there something specific about X that caught your attention?")
_AI_OFFER = (
    r"\bis there (?:something|anything) (?:specific |particular |else )?(?:about|in|that|you|i can)\b[^.?!\n]{0,80}"
    r"(?:interest|caught|catch|attention|help|know|share|discuss|talk|ask|curious|wonder)"
    r"|\bi (?:might|may|could|can) (?:be able to )?(?:share|offer|provide|give) (?:you )?(?:some |a few )?(?:insights?|thoughts|advice|information|guidance|help)\b"
    r"|\bwhat (?:specifically |exactly |in particular )?(?:about [^.?!\n]{1,40} )?(?:caught|interests?|draws?|brings?) you\b"
    r"|\bwhat would you like (?:me )?to (?:know|talk|tell|share|discuss|do|say|explain)\b"
    r"|\bwould you like (?:me )?to (?:talk|chat|tell|share|explain|discuss|elaborate)\b"
    r"|\bif you(?:'d| would) like,? i (?:can|could|'d be happy)\b"
    r"|\bi(?:'m| am) (?:happy|glad|here) to (?:listen|talk|chat|share|discuss)\b"
    r"|\bhow (?:can|may|could) i (?:be of )?(?:help|assist|serve|support)\b"
    r"|\bfeel free to\b"
    r"|\bi'?m (?:curious|interested|eager) (?:to (?:know|hear|learn)|about)\b[^.?!\n]{0,40}\byou(?:r)?\b"
)
AI_SOFT = re.compile("(?:" + AI_SOFT.pattern + ")|(?:" + _AI_OFFER + ")", AI_SOFT.flags)
GUSH = re.compile(r"\b(?:so sweet of you|thank you so much|you(?:'re| are) (?:so )?(?:amazing|wonderful|incredible)|i(?:'m| am) so (?:sorry|grateful|honou?red)|that means (?:so much|the world))\b", re.I)
HARSH = re.compile(r"\b(?:idiot|stupid|pathetic|moron|shut up|worthless|loser|disgusting)\b", re.I)
SLANG = re.compile(r"\b(?:gonna|wanna|gotta|yeah|yep|nah|dunno|kinda|sorta|lol|omg|ya|y'all|ain't|lemme|gimme)\b", re.I)
FORMAL_MARK = re.compile(r"\b(?:indeed|shall|perhaps|kindly|furthermore|therefore|nevertheless|hence|moreover|certainly|regrettably|pray)\b", re.I)
PROFANITY = re.compile(r"\b(?:fuck\w*|shit\w*|damn\w*|bitch\w*|asshole|bastard|crap|piss\w*|dick|bloody|goddamn)\b", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B06\u2764]")
CONTRACTION = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.I)
LIST_LINE = re.compile(r"^\s*(?:[-*•]\s+\S|\d+[.)]\s+\S|#{1,4}\s+\S|```)", re.M)

# ---------------------------------------------------------------- self-statements worth remembering
CANON_PATTERNS = [re.compile(p, re.I) for p in (
    r"\bI(?:'m| am) (?:a|an|the) (?!bit\b|little\b|lot\b|mess\b|wreck\b|bad\b day)[^.!?\n,;]{2,50}",
    r"\bI(?:'m| am) (?:from|born in|originally from|\d{1,3}\b(?: years old)?|allergic to|afraid of|scared of|terrible at|good at|bad at|great at|no good at|the type)[^.!?\n,;]{0,50}",
    r"\bI (?:really |absolutely |totally )?(?:love|hate|can't stand|cannot stand|prefer|adore|despise|detest|dislike|never eat|never drink|don't (?:like|eat|drink|do|believe in|trust))\b[^.!?\n]{2,60}",
    r"\bI (?:always|never|usually|rarely|only)\b[^.!?\n]{3,60}",
    r"\bI (?:grew up|used to|was born|was raised|once|lived|worked|studied|have (?:a|an|two|three|four|\d+) (?:brother|sister|dog|cat|kid|son|daughter|sibling|child|children|job|degree))\b[^.!?\n]{0,70}",
    r"\bmy (?:name|brother|sister|mother|mom|mum|father|dad|friend|best friend|boss|ex|husband|wife|boyfriend|girlfriend|dog|cat|job|favou?rite|birthday|house|apartment|car|hometown)\b[^.!?\n]{2,60}",
    r"\bI (?:promise|swear|vow)\b[^.!?\n]{2,60}",
    r"\bI(?:'ll| will| won't) (?:ever |never |always )[^.!?\n]{2,60}",
)]
TRANSIENT = re.compile(r"\b(?:right now|today|tonight|at the moment|this (?:morning|evening|week)|just now|a bit|a little|kind of|sort of)\b", re.I)
