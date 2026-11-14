"""The browser UI. The files under crumble/web are stitched into one page, so guests and the host get
exactly one response and nothing else needs to be served (or protected).

    web/index.html      the page shell (markup only)
    web/css/NN-*.css    styles, concatenated in filename order
    web/js/NN-*.js      scripts, concatenated in filename order (they share one global scope, like one big script)
    web/login.html      the guest sign-in page

Set CRUMBLE_DEV=1 to re-read the files on every request while you edit them.
"""
import os
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
_cache = {}


def _read(*parts):
    return (WEB.joinpath(*parts)).read_text(encoding="utf-8")


def _bundle(folder, pattern):
    return "\n".join((p.read_text(encoding="utf-8")).rstrip("\n") for p in sorted((WEB / folder).glob(pattern)))


def _build_page():
    return _read("index.html").replace("<!--STYLES-->", _bundle("css", "*.css")).replace("<!--SCRIPTS-->", _bundle("js", "*.js"))


def _get(key, build):
    if os.environ.get("CRUMBLE_DEV") or key not in _cache:
        _cache[key] = build().encode("utf-8")
    return _cache[key]


def page_bytes():
    return _get("page", _build_page)


def login_bytes():
    return _get("login", lambda: _read("login.html"))
