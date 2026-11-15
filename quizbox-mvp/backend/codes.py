from __future__ import annotations

import secrets

# Exclude characters that are easy to confuse when a code is read aloud.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_join_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
