"""Command line entry point: options, model auto-load, banner, and the server loop."""
import argparse
import secrets
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from .config import LLM, LLM_VERBOSE, MODELS, ROOT, GPU_HELP, Llama, gpu_status
from .server import H
from .sharing import SHAREF, SHARE, lan_urls, save_share
from .storage import rj, wj


def main():
        ap = argparse.ArgumentParser(description="Crumble: local character chat. Add --share to let other people use your AI.")
        ap.add_argument("--host", default="127.0.0.1")
        ap.add_argument("--port", type=int, default=8000)
        ap.add_argument("--share", action="store_true", help="listen on your network so friends can join (asks them for a password)")
        ap.add_argument("--password", help="guest password (default: random, remembered in data/share.json)")
        ap.add_argument("--no-password", action="store_true", help="let anyone with the link in, no password")
        ap.add_argument("--model", help="load this .gguf at startup (default: the model you used last time)")
        ap.add_argument("--max-guests", type=int, help="most guests allowed (default 8)")
        a = ap.parse_args()
        saved = rj(SHAREF, {}) or {}
        SHARE.update(port=a.port, max=a.max_guests or saved.get("max", 8), listen=a.share or a.host not in ("127.0.0.1", "localhost", "::1"))
        SHARE["on"] = SHARE["listen"]
        if SHARE["on"]:
            SHARE["password"] = "" if a.no_password else (a.password or saved.get("password") or secrets.token_urlsafe(6))
            save_share()
        _gpu, _ver = gpu_status()
        if Llama is not None:
            print(f"llama-cpp-python {_ver}: GPU offload " + ("AVAILABLE" if _gpu else "NOT available"))
            if not _gpu:
                print(GPU_HELP)
        last = rj(ROOT/"data"/"last_model.json", {}) or {}
        mp = a.model or last.get("path")
        if mp and Llama is not None and Path(mp).exists():
            print(f"Loading model {mp} ... (this can take a while)")
            try:
                # CHANGE n_gpu_layers to -1 here
                LLM["obj"] = Llama(model_path=mp, n_ctx=int(last.get("n_ctx", 8192)), n_gpu_layers=-1, verbose=LLM_VERBOSE)
                LLM["path"], LLM["n_ctx"] = mp, int(last.get("n_ctx", 8192))
                wj(ROOT/"data"/"last_model.json", {"path": mp, "n_ctx": LLM["n_ctx"], "n_gpu": -1})
                print("Model ready." + ("  (running on the GPU)" if gpu_status()[0] else "  (running on the CPU)"))
            except Exception as e:
                print("Could not load the model:", e)
        elif a.share:
            print("No model loaded yet. Load one from the sidebar on this PC before guests chat.")
        host = "0.0.0.0" if a.share and a.host == "127.0.0.1" else a.host
        url = f"http://127.0.0.1:{a.port}"
        print(f"Crumble running at {url}  (models in {MODELS})")
        if SHARE["on"]:
            print("\n  SHARING IS ON. Others can open:")
            for u in lan_urls(a.port) or [f"http://<this-pc-ip>:{a.port}"]:
                print("    " + u)
            print(f"  Password: {SHARE['password'] or '(none)'}   Max guests: {SHARE['max']}")
            print("  Same Wi-Fi/LAN works as is. For the internet use a tunnel (cloudflared / ngrok) or port-forward; the tunnel gives you https.")
            print("  Manage guests from the Settings tab on this PC.\n")
        threading.Timer(.8, lambda: webbrowser.open(url)).start()
        srv = ThreadingHTTPServer((host, a.port), H)
        srv.daemon_threads = True
        srv.serve_forever()
