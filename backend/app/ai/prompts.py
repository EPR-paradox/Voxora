"""Prompt files and their versions (design §8.5).

Prompt text lives in ``app/ai/prompts/*.txt`` under an explicit version name. The version string
recorded
in the database is the file name with underscores replaced by hyphens, so a stored evaluation can
always be
traced back to the exact prompt text that produced it.
"""

from functools import cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

EVALUATION_PROMPT_FILE = "evaluation_english_v1.txt"
EVALUATION_PROMPT_VERSION = "evaluation-english-v1"


@cache
def load_prompt(filename: str) -> str:
    """Read a prompt file once per process. Missing prompts are a startup-time bug, not a request
    error."""
    path = PROMPT_DIR / filename
    if not path.is_file():
        raise RuntimeError(f"Prompt file {filename!r} is missing from {PROMPT_DIR}.")
    return path.read_text(encoding="utf-8").strip()
