# Letting others use your AI

1. Start Crumble in share mode: double-click `Share.bat` (Windows) or run `./share.sh` (Mac/Linux),
   or run `python Crumble.py --share`. Allow network access if Windows asks.
2. Load your model on your own PC (Model box in the sidebar > Load model). Crumble remembers it and loads it automatically next time
   (or start with `--model path/to/model.gguf`). Guests see "host has not loaded a model" until this is done.
3. The console prints a link such as `http://192.168.1.20:8000` and a password. Send both to your guests.
   Same Wi-Fi/network works right away.
4. Manage everything in Settings > "Share with others": pause sharing, change the password, set the
   guest limit, see who is online, kick people.

Friends on the internet: run a tunnel (`cloudflared tunnel --url http://localhost:8000` or ngrok) and send
them the https link it prints. Port-forwarding also works but is plain http, so use a strong password.

What guests can do: chat, keep their own private chats and memories. What they cannot do: load models, create,
edit or delete characters, see character prompts and secrets, or change your settings.
Everyone shares your one model, so replies queue up (guests see "waiting in line").

Options: `--password X`, `--no-password`, `--max-guests N`, `--port N`.

Note: opening the share link on your own PC still counts as you (the host), so you keep full control there.
