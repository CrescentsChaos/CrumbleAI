import os
import sys
import tempfile
from pathlib import Path

# Isolated data folder, set before crumble.config is imported.
os.environ["CRUMBLE_HOME"] = tempfile.mkdtemp(prefix="crumble-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
