import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from crumble.config import LLM

SHY = {"id": "shy", "name": "Mira", "personality": "shy, quiet and anxious; very guarded, slow to trust, soft-spoken",
       "flaws": "easily upset, overthinks everything", "triggers": "being laughed at, loud crowds",
       "comfort": "tea, quiet music", "likes": "books, rain", "texting": "all lowercase, no emoji",
       "consistency": "Never swears\nAlways speaks in lowercase"}
BOLD = {"id": "bold", "name": "Rex", "personality": "bold, loud, sarcastic and proud; stubborn, witty, not shy",
        "flaws": "arrogant, hot-headed", "triggers": "being ignored", "humor": "dry sarcasm and teasing"}
BLANK = {"id": "blank", "name": "Pat"}


class FakeLLM:
    """Stands in for llama_cpp.Llama: scripted replies for chat, canned JSON for the mood tracker."""

    def __init__(self, replies=None, track=None):
        self.replies, self.track, self.calls = list(replies or ["Fine."]), track or {}, []

    def tokenize(self, b, add_bos=False):
        return b.split()

    def create_chat_completion(self, messages, stream=False, **kw):
        self.calls.append(messages)
        if not stream:
            ask = messages[-1]["content"]
            if "JSON" in ask:
                return {"choices": [{"message": {"content": json.dumps(self.track)}, "finish_reason": "stop"}]}
            return {"choices": [{"message": {"content": "A short summary."}, "finish_reason": "stop"}]}
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return iter([{"choices": [{"delta": {"content": text}, "finish_reason": None}]},
                     {"choices": [{"delta": {}, "finish_reason": "stop"}]}])


def install(fake):
    LLM["obj"], LLM["path"] = fake, "fake.gguf"
    return fake


def serve():
    from crumble.server import H
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def call(srv, method, path, body=None, host=None):
    c = HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Content-Type": "application/json"}
    if host:
        h["Host"] = host
    c.request(method, path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse()
    data = r.read().decode()
    try:
        return r.status, json.loads(data)
    except ValueError:
        return r.status, data


def ptxt(msgs):
    """The whole prompt text the model gets: the fixed system message plus the newest turn, which now carries what changes every turn
    (the private background, mood, time, style, variety). Tests that look for a block anywhere in the prompt read this."""
    return msgs[0]["content"] + "\n\n" + msgs[-1]["content"]
