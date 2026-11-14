#!/usr/bin/env python3
"""
Crumble - a local character-chat app for .gguf models (SillyTavern-style).

Setup:   pip install llama-cpp-python
         (GPU: CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir)
Run:     python Crumble.py            then open http://127.0.0.1:8000
Models:  drop .gguf files in ./models, or paste a full path in the UI.
Data:    ./data/characters/*.json, ./data/chats/<character>/*.json

This file only starts the app; the code lives in the ./crumble package (python -m crumble works too).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crumble.app import main  # noqa: E402

if __name__ == "__main__":
    main()
