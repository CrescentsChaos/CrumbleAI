"""Paths, shared state and the character-sheet schema."""
import os
# Let a CUDA build of llama-cpp-python find the CUDA DLLs (any installed toolkit, or CUDA_PATH).
if hasattr(os, "add_dll_directory"):
    _cuda_dirs = []
    if os.environ.get("CUDA_PATH"):
        _cuda_dirs.append(os.path.join(os.environ["CUDA_PATH"], "bin"))
    _tk = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if os.path.isdir(_tk):
        _cuda_dirs += [os.path.join(_tk, v, "bin") for v in sorted(os.listdir(_tk), reverse=True)]
    for _d in _cuda_dirs:
        if os.path.isdir(_d):
            try:
                os.add_dll_directory(_d)
            except OSError:
                pass
import threading
from pathlib import Path

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None


def gpu_status():
    """(can this llama-cpp-python build use the GPU?, version). A pip-installed CPU build says False."""
    try:
        import llama_cpp
        fn = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        return (bool(fn()) if fn else False), getattr(llama_cpp, "__version__", "?")
    except Exception:
        return False, "?"


GPU_HELP = """
  ============================================================================
   WARNING: this llama-cpp-python is a CPU-ONLY build, so the model runs on the CPU
   (your GPU will stay idle no matter what "GPU layers" is set to).

   Reinstall it with CUDA support (Windows PowerShell, needs the CUDA Toolkit and
   Visual Studio Build Tools with "Desktop development with C++"):

       pip uninstall -y llama-cpp-python
       $env:CMAKE_ARGS = "-DGGML_CUDA=on"
       pip install llama-cpp-python --force-reinstall --no-cache-dir

   (cmd.exe:  set CMAKE_ARGS=-DGGML_CUDA=on   then the same pip install.)
   Then start Crumble again; this warning disappears when the GPU is usable.
  ============================================================================
"""

# project folder (holds data/ and models/); CRUMBLE_HOME overrides it, e.g. for tests or a shared install
ROOT = Path(os.environ.get("CRUMBLE_HOME") or Path(__file__).resolve().parent.parent)
CHARS, CHATS, MODELS, GROUPS = ROOT/"data"/"characters", ROOT/"data"/"chats", ROOT/"models", ROOT/"data"/"groups"
for d in (CHARS, CHATS, MODELS, GROUPS):
    d.mkdir(parents=True, exist_ok=True)
LLM = {"obj": None, "path": None, "n_ctx": 8192}
LLM_VERBOSE = bool(os.environ.get("CRUMBLE_LLM_LOG"))   # set CRUMBLE_LLM_LOG=1 to see llama.cpp's own log (shows "offloaded N/N layers to GPU")
LOCK = threading.Lock()
CH, US = "{{char}}", "{{user}}"

# (section, [(key, label, rows)]) - the editor and the prompt builder both read this.
SCHEMA = [
    ("Core", [("name", "Name", 1), ("description", "Description", 5),
              ("personality", "Personality", 3), ("scenario", "Scenario", 3)]),
    ("Identity", [("age", "Age", 1), ("gender", "Gender / pronouns", 1), ("species", "Species / race", 1),
                  ("occupation", "Occupation", 1), ("skills", "Skills & abilities", 2),
                  ("knowledge", "What they know (and don't know)", 2)]),
    ("Look and voice", [("appearance", "Appearance", 3), ("speech", "Speech style", 3), ("quirks", "Habits & quirks", 2)]),
    ("Voice and manner", [("catchphrases", "Catchphrases & verbal tics", 2),
                          ("vocab", "Vocabulary, slang & swearing level", 2),
                          ("dialect", "Accent, dialect, languages mixed in", 2),
                          ("texting", "Texting habits (caps, emoji, punctuation, message length)", 2),
                          ("mood_speech", "How their speech changes when happy / angry / nervous / sad", 3),
                          ("body_language", "Body language & tells", 2), ("humor", "Sense of humour", 1)]),
    ("Mind and history", [("backstory", "Backstory", 5), ("likes", "Likes", 2), ("dislikes", "Dislikes", 2),
                          ("goals", "Goals", 2), ("fears", "Fears", 2),
                          ("relationships", "Relationships", 3), ("secrets", "Secrets", 3),
                          ("values", "Values & beliefs", 2), ("flaws", "Flaws & bad habits", 2),
                          ("triggers", "Triggers (what sets them off)", 2),
                          ("comfort", "What comforts or cheers them up", 2),
                          ("boundaries", "Boundaries & dealbreakers", 2)]),
    ("Roleplay", [("stats", "Stats: STR DEX CON INT WIS CHA (3-20, blank = 10 each), e.g. STR 12 DEX 14 CON 10 INT 9 WIS 11 CHA 13", 1),
                  ("combat", "Fighting style, weapons, armor, powers", 2),
                  ("romance", "Romance: how they flirt, what they want, how fast they warm up, dealbreakers", 3),
                  ("talk", "Talkativeness in group chats (0-100, or quiet / normal / chatty; blank = guessed from the sheet)", 1)]),
    ("Personality", [("traits", "Personality traits: numbers 0-100 (O 70 C 40 E 85 A 30 N 60, or warmth: high) and/or adjectives (sarcastic, guarded, loyal). Blank = read from the sheet", 2),
                     ("reactions", "How they react: to kindness, rudeness, being ignored, praise, being challenged, someone upset", 3),
                     ("consistency", "Hard rules, one per line: Never swears / Always speaks in lowercase / Never says \"sorry\"", 3)]),
    ("Chat setup", [("first_mes", "First message", 4), ("alts", "Alternate greetings (separate with a line of ---)", 4),
                    ("mes_example", "Example dialogue", 6), ("system_prompt", "System prompt override", 3),
                    ("post_history", "Reminder placed after the chat history", 2),
                    ("tags", "Tags (comma separated)", 1), ("notes", "Creator notes", 2)]),
]
KEYS = [k for _, fs in SCHEMA for k, _, _ in fs]
PERS_KEYS = ("traits", "reactions", "consistency")   # read by the personality engine instead of being pasted into the prompt
EXT_KEYS = [k for sec, fs in SCHEMA if sec not in ("Core", "Chat setup") for k, _, _ in fs]

EMO = {"neutral": "😐", "happy": "😊", "joyful": "😄", "excited": "🤩", "amused": "😄", "playful": "😏", "smug": "😏",
       "proud": "😎", "confident": "😎", "determined": "😤", "relaxed": "😌", "content": "😌", "calm": "😌",
       "affectionate": "🥰", "fond": "🥰", "grateful": "🙏", "hopeful": "🤞", "curious": "🤔", "thoughtful": "🤔",
       "skeptical": "🤨", "surprised": "😮", "confused": "😕", "flustered": "😳", "embarrassed": "😳", "shy": "😳",
       "nervous": "😬", "anxious": "😟", "worried": "😟", "sad": "😢", "lonely": "🥺", "hurt": "💔", "guilty": "😔",
       "tired": "😴", "sleepy": "😴", "bored": "🥱", "annoyed": "😒", "irritated": "😒", "frustrated": "😤",
       "angry": "😠", "furious": "🤬", "jealous": "😒", "disgusted": "🤢", "scared": "😨", "serious": "😐"}
STAGES = [(12, "hostile toward them"), (28, "cold and wary"), (42, "distant and guarded"),
          (58, "neutral, still getting to know them"), (72, "friendly and comfortable with them"),
          (86, "fond of them and close"), (101, "deeply attached and trusting")]
STOPW = set("the a an i you to and of it is in that for on with my your me we this be are was do have just so but not "
            "what its im dont no yes if or at as he she they them his her like".split())
