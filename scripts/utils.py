from __future__ import annotations

import re

_NON_DIGIT_RE = re.compile(r"\D")


def only_digits(value: str) -> str:
    return _NON_DIGIT_RE.sub("", value)
