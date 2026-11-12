# 🍪 Crumble

**A local character-chat app for `.gguf` models.** Crumble runs entirely on your own computer. Pick a character, load a model, and chat in your browser. Characters have moods, memory, a sense of time and their own way of talking. You can also share it with friends so they use the AI running on *your* PC.

No cloud, no accounts, no API keys. One Python file.

---

## Features

### Characters that feel real
- **Mood and relationship** - after every reply the character updates how it feels (shown as an emoji chip) and how much it likes you. That changes its tone, warmth and patience over time.
- **Long-term memory** - it remembers facts about you and automatically summarises long chats, so it doesn't forget what happened earlier. Everything is viewable and editable in the **Memory** tab.
- **Time awareness** - it knows the date, the time of day, and how long it's been since you last spoke.
- **Secrets that stay secret** - private character info is only hinted at or revealed once trust is high enough.
- **Inner thoughts** - optionally see a private thought under each message.
- **Natural speech** - prompts push the model away from "AI assistant" talk: contractions, opinions, moods, fillers, no repeating the same openings. Reply length mirrors yours. Repetitive replies are detected and regenerated.
- **Deep character sheets** - on top of the usual fields: catchphrases, slang, dialect, texting habits, how their speech changes when happy/angry/nervous, body language, humour, values, flaws, triggers, boundaries and more.
- **Initiative (optional)** - the character can text you first if you go quiet.

### Chat that feels like chatting
- **Replies are generated in full first**, then typed out like a person (variable speed, pauses at punctuation). Click or press `Esc` to skip.
- **Never cut off mid-sentence** - replies are trimmed to a complete sentence if they hit the length limit, and dangling `*actions*`, `"quotes"` and `(asides)` are repaired.
- **Three modes** - 🎭 Roleplay (actions + dialogue), 💬 Texting (separate message bubbles, occasional typos that get corrected) and 📞 Voice call.
- Timestamps, read receipts, date separators, emoji reactions the character notices.
- Alternate replies (swipes), Continue, edit / delete / rewind any message, scene notes to steer the story.
- Read-aloud (browser voices) and voice dictation, avatars, light/dark theme, multiple chats per character, chat export.
- Tavern **Character Card V2** import/export (JSON and PNG), lorebook, AI-drafted characters.
- **Mobile-friendly** - drawer menu, bottom tabs, compact header, keyboard-aware layout.

### Share it with friends
Run it with `--share` and others can chat with your characters from their own browser, using the model on your PC. See [Sharing](#sharing-your-ai-with-others).

---

## Quick start

**Requirements:** Python 3.9+ and a `.gguf` model (for example from [Hugging Face](https://huggingface.co/models?library=gguf)).

```bash
git clone https://github.com/<your-username>/CrumbleAI.git
cd CrumbleAI
pip install llama-cpp-python
python Crumble.py
```

Your browser opens at `http://127.0.0.1:8000`.

1. Put a `.gguf` file in the `models/` folder (or paste its full path in the UI).
2. In the sidebar open **Load a .gguf**, choose it and press **Load model**.
3. Pick a character and start talking. Crumble remembers your last model and loads it automatically next time.

**GPU acceleration (NVIDIA):**
```bash
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir
```
Then leave *GPU layers* at `-1` to offload everything.

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
  chats/<character>/ your chats, including mood, memory and settings per chat
  chats/<character>_<guest id>/   guests' private chats (share mode)
  last_model.json    the model to auto-load next time
  share.json         guest password and limit
  sessions.json      guest sessions
```

Back up or delete that folder to keep or wipe everything. Settings such as theme and sampler values are saved in your browser.

---

## Tips

- **Replies feel flat?** Raise `temperature` a little in **Settings → Generation**, and turn **Realism rules** and **Emotions and memory** on.
- **Slow on a weak PC?** Turn off **Emotions and memory** (it makes one small extra model call after each reply) and **Thinking**.
- **Model template errors about the first message?** Enable *Fold the greeting into the system prompt* in Settings.
- **Context too small for long chats?** Load the model with a bigger context length. Old messages are summarised and trimmed automatically either way.

## Project layout

```
Crumble.py     the whole app: server, prompt building and web UI
Share.bat      Windows launcher for share mode
share.sh       Mac/Linux launcher for share mode
SHARING.md     hosting guide
data/          characters, chats and settings
models/        put your .gguf files here
```

## Contributing

Issues and pull requests are welcome. The app is intentionally a single dependency-light file (`llama-cpp-python` is the only requirement), so please keep it that way.

## License

Add a license for your repo (for example MIT) as `LICENSE`.
