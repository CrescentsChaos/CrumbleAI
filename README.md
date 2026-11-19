# 🍪 Crumble

**A local character-chat app for `.gguf` models.** Crumble runs entirely on your own computer. Pick a character, load a model, and chat in your browser. Characters have moods, memory, a sense of time and their own way of talking. You can also share it with friends so they use the AI running on *your* PC.

No cloud, no accounts, no API keys. A small Python package whose only dependency is `llama-cpp-python`.

---

## Features

### Characters that feel real
- **Mood and relationship** - after every reply the character updates how it feels (shown as an emoji chip) and how much it likes you. That changes its tone, warmth and patience over time.
- **Long-term memory** - it remembers facts about you and automatically summarises long chats, so it doesn't forget what happened earlier. Everything is viewable and editable in the **Memory** tab.
- **Hierarchical memory** - four layers instead of one blob. **Short-term** (the scene right now and what just happened), **episodic** (important events between you, e.g. "{{user}} gave her a necklace on her birthday"), **semantic** (lasting facts about you, them and your relationship, e.g. "{{user}} dislikes being interrupted") and **emotional** (how the character remembers feeling, e.g. "she felt embarrassed when you found her secret", linked to the event). Nothing is pasted wholesale: each reply, Crumble reads your latest message (people, topics, kind of event, feeling), searches the memories, ranks them by relevance, recency and importance, and injects only the best few (**Settings -> Memory**: light / standard / deep). Memories are written after replies and, for important moments (gifts, promises, fights, confessions, \"remember this\"), with one extra small model call; a plain note is kept if the model gives nothing usable. The **Memory** tab shows and edits every layer, pins memories, explains *why* something is recalled (**Try a message**), and can **Build memories from this chat** for existing chats. Rewinding or swiping a reply undoes what it taught.
- **Time awareness** - it knows the date, the time of day, and how long it's been since you last spoke.
- **Secrets that stay secret** - private character info is only hinted at or revealed once trust is high enough.
- **Inner thoughts** - optionally see a private thought under each message.
- **Natural speech** - prompts push the model away from "AI assistant" talk: contractions, opinions, moods, fillers, no repeating the same openings. Reply length mirrors yours. Repetitive replies are detected and regenerated.
- **Deep character sheets** - on top of the usual fields: catchphrases, slang, dialect, texting habits, how their speech changes when happy/angry/nervous, body language, humour, values, flaws, triggers, boundaries and more.
- **Initiative (optional)** - the character can text you first if you go quiet.

### A personality that stays consistent
Small local models drift: a shy character turns chatty, a blunt one turns polite, and anyone can slip into "happy to help!" assistant talk. The **personality engine** (on by default, tune it in **Settings → Personality engine**) works around that without extra model calls for the common case.

- **Traits read from the sheet.** Crumble turns the Personality, Flaws, Quirks, Humour, Speech and Texting fields into 14 stable dials: the five broad traits (openness, conscientiousness, extraversion, agreeableness, emotional volatility) plus assertiveness, warmth, humour, formality, talkativeness, impulsiveness, openness to trust, pride and expressiveness. Negations ("not shy") and intensifiers ("very guarded") are understood. Open the **Personality profile** panel in the character editor to see what it found and why.
- **You stay in charge.** Fill the new **Traits** field to override the guesses (`O 70 C 40 E 85 A 30 N 60`, or `warmth: high, pride: very low`, or plain adjectives like `sarcastic, guarded`). **How they react** and **Consistency** (hard rules such as `Never swears` or `Always speaks in lowercase`) are read by the engine and enforced.
- **Reactions that depend on who they are.** The prompt describes how this character behaves in every scene, and reacts to what you just did: an insult, kindness, a compliment, a challenge, an apology, you opening up. A proud, blunt character fires back; a timid one withdraws. Anything matching their **Triggers**, **Boundaries**, **Fears** or **Comforts** is noticed even when you word it differently ("laughing at you" matches *being laughed at*).
- **Mood that moves like they would.** Mood and affection changes proposed by the model are bounded and shaped by temperament: a stoic does not jump to fury in one message, a thin-skinned character is hurt more by an insult, warmth is earned back slowly after a grudge, and time heals (come back tomorrow and the anger has cooled). Setting the mood by hand in the Memory tab is respected.
- **They remember what they said about themselves.** Durable statements ("I'm a nurse", "I hate cilantro", promises) are collected per chat, fed back into the prompt, and checked so the character does not contradict them later. Edit the list in **Memory → Personality**.
- **Consistency guard.** Each reply is scored 0-100 for assistant-speak, list formatting, wrong register (too formal or too casual for them), emoji against their habits, breaking a rule you wrote, contradicting an earlier statement, and wildly different length. A reply that scores too low is re-rolled with a targeted correction, up to twice, and the best attempt is kept. Turn on **Show consistency score** for a badge on each message; the Memory tab charts the trend.

Depth **Light**, **Standard** and **Deep** control how much is added to the prompt (Deep also adds a one-line reminder at the end, where models listen most). Characters without personality text are left alone. The Narrator never gets a personality. Guests cannot see profiles, because they are derived from the private sheet.

### Chat that feels like chatting
- **Replies are generated in full first**, then typed out like a person (variable speed, pauses at punctuation). Click or press `Esc` to skip.
- **Never cut off mid-sentence** - replies are trimmed to a complete sentence if they hit the length limit, and dangling `*actions*`, `"quotes"` and `(asides)` are repaired.
- **Three modes** - 🎭 Roleplay (actions + dialogue), 💬 Texting (separate message bubbles, occasional typos that get corrected) and 📞 Voice call.
- Timestamps, read receipts, date separators, emoji reactions the character notices.
- Alternate replies (swipes), Continue, edit / delete / rewind any message, scene notes to steer the story.
- Read-aloud (browser voices) and voice dictation, avatars, light/dark theme, multiple chats per character, chat export.
- Tavern **Character Card V2** import/export (JSON and PNG), lorebook, AI-drafted characters.
- **Mobile-friendly** - drawer menu, bottom tabs, compact header, keyboard-aware layout.

### A fresh look: themes, fonts and character cards
- **Per-chat themes.** Click the palette in a chat's header: 10 presets (Cocoa, Milk, Midnight, Rosé, Moss, Arcade, Parchment, Noir, Ember, Frost), any accent colour, surface tint, dark or light, backdrops (glow, aurora, dots, grid, lines, grain, stars, the character's portrait, or your own image), bubble style (soft, glass, outline, open page), message font, text size, corner roundness and spacing. It is saved with the chat. **Settings -> Appearance** sets the default for chats without their own style, and **Use for new chats** makes a style the starting point.
- **Fonts.** Bricolage Grotesque (headings), Figtree (interface), Literata (story text), JetBrains Mono. They are bundled in `crumble/web/fonts`, so the app looks the same offline.
- **Character cards.** The **Cards** tab is a gallery: each card takes its colour from the portrait, opens a card sheet (about, personality, scenario, opening line, chats), and can be exported as a Tavern V2 **JSON or PNG card**. Drop a JSON/PNG onto the gallery to import.
- **Faster chat.** Replies stream onto the page as they are written (no waiting for the whole reply, then typing it out). **Quick replies** (Settings -> Replies and sound) re-rolls at most once and only for real mistakes. Mood and memory updates wait until you have been quiet for a moment, so they never hold up your next message. Thinking is off by default for new installs. Stop keeps what was already written.

### Group chats and real roleplay
- **Group chats** - put two or more characters in one chat (**＋ New group** in the sidebar). Each one keeps their own mood, memory and personality, and only knows what they would know. Add an optional **Narrator** (a game-master voice) and a shared setting.
- **Realistic turn-taking** - not everyone answers everything. A "director" decides who speaks next from how chatty each character is (the new *Talkativeness* field, or guessed from their sheet), who was spoken to, what interests them and how fond they are of you. Quiet characters stay out of it, chatty ones jump in, the conversation winds down by itself, and a character can simply choose not to reply. Pick the **pace** per group: Quiet, Natural or Lively.
- **@mentions** - type `@` for an autocomplete menu (or click a face in the header). A mentioned character always answers; the others mostly stay out. `@everyone` gets the whole group. Characters can `@` each other too, and pull each other into the conversation. **💬 Let them talk** lets the group chat among themselves.
- **Action engine** - what you *do* now has consequences. Write actions naturally (`*punches Marcus*`, `I try to convince her`, `*kisses her cheek*`) or use the **🎲 Actions** buttons. Crumble rolls a d20 against your stats and the situation, shows the roll, and the characters must play out the result: a failed persuasion fails, a lucky stealth works. Turn it off or switch to buttons-only in **Settings → Roleplay engine**.
- **Real combat** - start a fight and you get HP bars, initiative, hit and miss rolls, damage, armor, defending, fleeing, using powers, healing, intimidating and talking people down. Enemies can lose their nerve and yield or flee; friends who like you jump in; bystanders react. The characters narrate what the dice decided (never the numbers). Fights never kill anyone: at 0 HP you are knocked out, and the story decides what happens next. Characters stay wounded until you rest.
- **Romance that takes time** - each character has a romance level with you that moves with your choices: flirt, tender touch, ask out, kiss, confess, get closer. Rushing gets a gentle (or firm) deflection, and personality matters (*slow burn* is harder than *flirty*). Milestones like the first kiss are remembered. Intimate scenes are always tasteful and fade to black, and romance is never used with a character whose age is under 18.
- **Stats** - set yours under **About you** and theirs in the **Roleplay** section of the character sheet: `STR 12 DEX 14 CON 10 INT 9 WIS 11 CHA 13` plus fighting style, gear and powers.
- **Slash commands** - `/roll 2d6+3`, `/fight Name`, `/peace`, `/rest`. Every roll has ↻ re-roll and ✕ ignore buttons.

### In character and out of character (IC / OOC)
You are both the player and the author. **IC** is what your character says and does, and the characters answer it. **OOC** is you talking to the **storyteller** (a co-author voice, not any character). The characters never hear OOC messages, and they never reach the memory or the summaries.

Switch with the **IC / OOC** button next to the message box (or `Alt+O`), or send a single OOC message with `((text))`, `//text` or `ooc: text`. `/ic` goes back in character; `/ooc`, `/discuss`, `/correct`, `/setting` and `/direct` switch mode (or send one message when followed by text).

| Kind | Use it to | What happens |
| --- | --- | --- |
| 💬 **Discuss** | Talk about the story: motives, pacing, what could happen next | The storyteller answers. Nothing in the scene changes. |
| 🛠 **Correct** | "Mira wouldn't say that, she's shy" | A standing rule for that character (name them in a group). It overrides contradicting habits. **↻ Redo the last reply** rewrites the reply with the rule. |
| 🌍 **Setting** | "Move the scene to the pier at sunset", "time skip to morning" | Becomes true for everyone from now on. |
| 🎬 **Direct** | "Have a stranger knock on the window" | Steers events without touching anyone's dialogue. Used once (in the next round of replies), or always if you say "from now on". |

**Auto** (default) reads which kind you meant; click the tag under a message to change it. Corrections, settings and directions are kept as **author's notes**: see, edit, make standing, or remove them in **Memory → Author's notes**. Deleting or rewinding the OOC message removes its note. Characters follow the notes silently and never mention them. **▶ Continue the scene** goes back in character with your notes applied. In **Settings → Out of character** you can make the storyteller stay silent for corrections, settings and directions.

### Share it with friends
Run it with `--share` and others can chat with your characters from their own browser, using the model on your PC. See [Sharing](#sharing-your-ai-with-others).

---

## Quick start

**Requirements:** Python 3.9+ and a `.gguf` model (for example from [Hugging Face](https://huggingface.co/models?library=gguf)).

```bash
git clone https://github.com/CrescentsChaos/CrumbleAI.git
cd CrumbleAI
.\venv\Scripts\Activate.ps1
$env:CMAKE_ARGS = "-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=86"
$env:CMAKE_BUILD_PARALLEL_LEVEL = "6"
pip install llama-cpp-python --force-reinstall --no-cache-dir
python Crumble.py
```

Your browser opens at `http://127.0.0.1:8000`.

1. Put a `.gguf` file in the `models/` folder (or paste its full path in the UI).
2. In the sidebar open **Load a .gguf**, choose it and press **Load model**.
3. Pick a character and start talking. Crumble remembers your last model and loads it automatically next time.

**GPU acceleration (NVIDIA):** a plain `pip install llama-cpp-python` gives a **CPU-only** build (the GPU stays idle).
Crumble prints `GPU offload AVAILABLE / NOT available` at startup and shows `(GPU)` or `CPU ONLY build` in the sidebar.
To get the GPU build on Windows (needs the CUDA Toolkit and Visual Studio Build Tools with the C++ workload), in PowerShell:
```powershell
pip uninstall -y llama-cpp-python
$env:CMAKE_ARGS = "-DGGML_CUDA=on"
pip install llama-cpp-python --force-reinstall --no-cache-dir
```
(cmd.exe: `set CMAKE_ARGS=-DGGML_CUDA=on`. Linux/Mac: `CMAKE_ARGS="-DGGML_CUDA=on" pip install ...`.)
Leave *GPU layers* at `-1` to offload everything. Set `CRUMBLE_LLM_LOG=1` to see llama.cpp's own log
(look for "offloaded N/N layers to GPU"). In Task Manager the GPU graph defaults to *3D*; switch one of the
graphs to **Cuda** (or run `nvidia-smi`) to see the model working.

### Command-line options

| Option | Meaning |
| --- | --- |
| `--port N` | Port to use (default `8000`) |
| `--model PATH` | Load this `.gguf` at startup |
| `--share` | Let other people connect (see below) |
| `--password X` | Guest password (default: random, remembered) |
| `--no-password` | Let anyone with the link in |
| `--max-guests N` | Most guests at once (default `8`) |

---

## Sharing your AI with others

Start Crumble in share mode: double-click **`Share.bat`** (Windows), run **`./share.sh`** (Mac/Linux), or run `python Crumble.py --share`.

The console prints a link and a password. Send both to your friends. On the same Wi-Fi/network it works immediately.

**Over the internet** the safest route is a tunnel, which gives you an https link and needs no router setup:
```bash
cloudflared tunnel --url http://localhost:8000
```
(ngrok works too.) Port-forwarding also works, but it's plain http, so use a strong password.

**Manage guests** in **Settings → Share with others** on your PC: pause sharing, change the password, set the guest limit, see who's online, kick people.

| Guests **can** | Guests **cannot** |
| --- | --- |
| Chat with characters | Load or change models |
| Keep their own private chats and memories | Create, edit or delete characters |
| Use their own settings | See character prompts, backstories or secrets |

Everyone shares your one model, so replies queue up ("waiting in line"). Opening the share link on your own PC still counts as you, the host. Connections coming through a tunnel are always treated as guests.

More detail in [`SHARING.md`](SHARING.md).

---

## Characters

Characters live in `data/characters/*.json` and are edited in the **Character** tab. You can:

- Import a Tavern Character Card V2 (`.json`, or a `.png` with embedded card data). PNG cards also provide the avatar.
- Drop a card file straight into `data/characters/`. Crumble converts it on first launch and keeps your original as `.json.bak`.
- Export any character as a V2 card (Crumble-specific fields are stored under `extensions.hearth`).
- Describe a character in a sentence and let the loaded model **draft** the whole sheet.

## Your data

Everything stays on your machine, in the `data/` folder:

```
data/
  characters/        character sheets (.json)
  groups/            group chat setups (.json)
  chats/<character>/ your chats, including mood, memory, fights and romance per chat
  chats/<group id>/  group chats
  chats/<character>_<guest id>/   guests' private chats (share mode)
  last_model.json    the model to auto-load next time
  share.json         guest password and limit
  sessions.json      guest sessions
```

Back up or delete that folder to keep or wipe everything. Settings such as theme and sampler values are saved in your browser.

---

## Tips

- **Replies feel flat?** Raise `temperature` a little in **Settings → Generation**, and turn **Realism rules** and **Emotions and memory** on.
- **Slow on a weak PC?** Turn off **Emotions and memory** (it makes one small extra model call after each reply) and **Thinking**. Turn off **Consistency guard** too if replies are being re-rolled often, or set the personality depth to Light.
- **Character keeps acting off-type?** Describe them in plain adjectives in **Personality**, or put numbers in **Traits**, add a couple of lines under **Consistency**, and check the **Personality profile** panel to see whether Crumble understood.
- **Model template errors about the first message?** Enable *Fold the greeting into the system prompt* in Settings.
- **Context too small for long chats?** Load the model with a bigger context length. Old messages are summarised and trimmed automatically either way.

## Project layout

```
Crumble.py         starts the app (python -m crumble does the same)
crumble/
  config.py        paths, shared state, the character-sheet schema
  storage.py       characters, groups and chats on disk
  textutil.py      reply clean-up, repetition checks, JSON recovery
  rp/              roleplay engine: dice, actions, combat, romance, group turn-taking
  personality/     personality engine: profile, stimulus, dynamics, canon, voice guard, prompt directives
  prompt.py        builds the messages the model sees
  llm.py           runs the model and the reply pipeline
  memory.py        mood, affection and long-term memory
  recall/          hierarchical memory: store, query analysis, ranked retrieval, learning (short-term / episodic / semantic / emotional)
  sharing.py       guest sessions, password, queue
  server.py        HTTP server and JSON API
  web.py, web/     the browser UI: index.html, css/NN-*.css, js/NN-*.js (joined in filename order)
  app.py           command-line options and startup
tests/             python -m unittest discover -s tests -t .
Share.bat          Windows launcher for share mode
share.sh           Mac/Linux launcher for share mode
SHARING.md         hosting guide
data/              characters, chats and settings
models/            put your .gguf files here
```

Environment variables: `CRUMBLE_HOME` moves `data/` and `models/` to another folder, `CRUMBLE_DEV=1` re-reads the UI files on every page load while you edit them, and `CRUMBLE_LLM_LOG=1` shows llama.cpp's own log.

## Contributing

Issues and pull requests are welcome. The app is intentionally dependency-light (`llama-cpp-python` is the only requirement; the tests use only the standard library), so please keep it that way. Run `python -m unittest discover -s tests -t .` before sending a change.

## License

Add a license for your repo (for example MIT) as `LICENSE`.

---

## Roleplay reliability (identity, leaks, narration, story time)

- **Identity separation.** The prompt states plainly who is who (the character, the user, everyone else), tells the character it never writes or decides for the user, and notes when the user's message dictates what the character does or feels (an *attempt*, not a fact). A reply that narrates the user (`*Crescent walks away*`) or echoes the user's message is retried.
- **No instruction leaks.** The end-of-prompt reminder is one delimited private note without brackets or "Reply as <name>" wording. Anything that still leaks (`[Reply as ...]`, `[As Faith]`, `<<note>>`, `(Write only ...)`) is stripped from the reply (`crumble/sanitize.py`), cut off at generation time by stop sequences, and retried when the model wrote as the user.
- **Narration format.** Everything that is not spoken dialogue is shown between `*asterisks*`; stray `(asides)` and `[asides]` become narration.
- **Story time.** `crumble/simtime.py` derives the clock from the story ("Monday morning", "three hours later", "the next morning", "at 3pm", author setting notes) every turn. The character gets the story clock instead of the PC's clock, the "time since last message" is story time, and replies that contradict it (night talk at noon) are retried. Without any time in the story, the real clock is used as before.

## Environmental awareness (`crumble/ambience.py`)

Derived from the whole chat every turn, like the identity ledger and the story clock: place (indoors/outdoors, with sensory palette), weather (with physics, indoors vs outdoors, persistence until the story changes it), light (follows the story clock) and tone (horror 0-2, tenderness/intimacy 0-2, weighted to the most recent messages). It adds an `[Environment]` block to the prompt, gives horror and intimate beats up to 30% more room, and retries replies that clearly break the scene (sunshine in a storm, rain soaking people indoors, rain from nowhere in clear weather, giggling in a horror beat). Intimacy only adds grounding and realism; the explicitness ceiling from the intimacy settings always wins.
