"""Value objects for report verification (SR06), designed for people copying from paper.

User analysis: verifiers type the code and digest from a printed report, so
both must survive spaces, line breaks, hyphens, case and look-alike glyphs.

* ``VerificationCode`` uses Crockford base-32 (no I, L, O or U), 28 symbols
  = 140 random bits (>= the 128 the SRS requires), printed in groups of four.
  Parsing upper-cases, drops separators and maps O→0 and I/L→1.
* ``Sha256Digest`` accepts the digest with any whitespace (the stub prints it
  in groups of four) and normalises it to 64 lowercase hex characters.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from .errors import Issue, ValidationFailed

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
SYMBOLS = 28
BITS = SYMBOLS * 5
_LOOKALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})
_SEPARATORS = re.compile(r"[\s\-_.]+")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class VerificationCode:
    """A canonical code such as ``7K2M-9QXD-4HPR-TV8W-3JNC-6GFA-2BZE``."""

    symbols: str

    def __post_init__(self) -> None:
        if len(self.symbols) != SYMBOLS or any(c not in ALPHABET for c in self.symbols):
            raise ValueError("A verification code has 28 Crockford base-32 symbols.")

    @classmethod
    def generate(cls) -> "VerificationCode":
        value = secrets.randbits(BITS)
        symbols = "".join(ALPHABET[(value >> (5 * i)) & 31] for i in reversed(range(SYMBOLS)))
        return cls(symbols)

    @classmethod
    def parse(cls, text: str) -> "VerificationCode | None":
        """Read a code as a person typed it. ``None`` if it cannot be a Folio code."""
        symbols = _SEPARATORS.sub("", str(text or "")).upper().translate(_LOOKALIKES)
        try:
            return cls(symbols)
        except ValueError:
            return None

    def __str__(self) -> str:
        return "-".join(self.symbols[i:i + 4] for i in range(0, SYMBOLS, 4))


@dataclass(frozen=True)
class Sha256Digest:
    hex: str

    @classmethod
    def parse(cls, text: str, field: str = "sha256_hex") -> "Sha256Digest":
        compact = re.sub(r"\s+", "", str(text or "")).lower()
        if not _HEX64.fullmatch(compact):
            raise ValidationFailed([Issue("invalid_digest",
                                          "SHA-256 digest must be exactly 64 hexadecimal characters.",
                                          field=field)])
        return cls(compact)

    def __str__(self) -> str:
        return self.hex
