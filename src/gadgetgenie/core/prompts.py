"""Load versioned prompt templates from the installed package (independent of the working directory)."""
from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources

SQL_PROMPT = "sql_v2.md"
SUMMARY_PROMPT = "summary_v2.md"


@lru_cache(maxsize=None)
def load(name: str) -> str:
    return (resources.files("gadgetgenie") / "prompts" / name).read_text(encoding="utf-8")


def render(name: str, **values: object) -> str:
    """Fill ``{{key}}`` placeholders. Plain replacement, so JSON braces in templates are safe."""
    text = load(name)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


_TAG_LIKE = re.compile(r"<(?=[/!?A-Za-z])")


def tag(name: str, value: str) -> str:
    """Wrap user-controlled text in a delimiter tag; anything that looks like a tag inside it is
    neutralized so it cannot close the delimiter (comparison operators like ``<=`` survive)."""
    return f"<{name}>{_TAG_LIKE.sub(chr(0x2039), value)}</{name}>"
