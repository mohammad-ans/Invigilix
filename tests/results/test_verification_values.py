"""SR06 value objects: codes and digests that survive being copied from paper."""
from __future__ import annotations

import re

import pytest

from backend.app.features.results.domain import Sha256Digest, ValidationFailed, VerificationCode
from backend.app.features.results.domain.verification import BITS

CANONICAL = re.compile(r"^[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){6}$")


def test_generated_codes_are_canonical_and_carry_enough_entropy():
    codes = {str(VerificationCode.generate()) for _ in range(200)}
    assert len(codes) == 200
    assert all(CANONICAL.match(c) for c in codes)
    assert BITS >= 128


@pytest.mark.parametrize("typed", [
    "7K2M-9QXD-4HPR-TV8W-3JNC-6GFA-2BZE",
    "7k2m 9qxd 4hpr tv8w 3jnc 6gfa 2bze",
    " 7K2M9QXD4HPRTV8W3JNC6GFA2BZE\n",
    "7K2M_9QXD.4HPR-TV8W 3JNC-6GFA-2BZE",
])
def test_codes_read_the_way_people_type_them(typed):
    assert str(VerificationCode.parse(typed)) == "7K2M-9QXD-4HPR-TV8W-3JNC-6GFA-2BZE"


def test_lookalikes_map_to_digits_and_impossible_codes_are_none():
    assert VerificationCode.parse("O1IL-0000-0000-0000-0000-0000-0000").symbols.startswith("0111")
    assert VerificationCode.parse("wrong-code") is None
    assert VerificationCode.parse("") is None


def test_digest_accepts_grouped_whitespace_and_rejects_bad_hex():
    hex64 = "66bc4f73eb5697cd252b3be988efde686a64a6b2e37a7edc2184840ff726591a"
    grouped = " ".join(hex64[i:i + 4] for i in range(0, 64, 4)).upper()
    assert Sha256Digest.parse(grouped).hex == hex64
    with pytest.raises(ValidationFailed) as refused:
        Sha256Digest.parse(hex64[:-1] + "z")
    assert refused.value.issues[0].field == "sha256_hex"
