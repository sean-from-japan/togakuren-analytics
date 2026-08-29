"""Controls for how much about a person leaves the local database.

The people in this dataset are amateur students, not professionals. The
federation publishes their names because it runs the competition; that is not
the same as a third party redistributing those names. So this module exists to
make the safe thing the easy thing, and to *measure* how safe a given choice
actually is rather than assuming.

Modes, weakest to strongest:

``full``
    Real names. Local analysis only.
``initials``
    ``山田 太郎`` becomes ``山.太.``, ``Alpha Player`` becomes ``A.P.``. Looks
    like protection and mostly is not — see :func:`k_anonymity`. Offered because
    it is what people reach for, and refused by :func:`check_public_safe`.
``pseudonym``
    A stable label derived from the player id and a salt. Consistent within one
    export, meaningless across exports unless the salt is reused.
``aggregate``
    Per-player rows are not emitted at all. Only group totals, which fall
    outside the Personal Information Protection Act entirely.
"""

import hashlib
import os
import re
from collections import Counter

MODES = ("full", "initials", "pseudonym", "aggregate")

#: Modes that may be used for anything published outside the local machine.
PUBLIC_SAFE_MODES = frozenset({"pseudonym", "aggregate"})

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class PrivacyError(ValueError):
    """Raised when an export would disclose more than the caller asked for."""


def new_salt():
    """A fresh random salt. Keep it out of the repository."""
    return os.urandom(16).hex()


def _initials(name):
    parts = [part for part in re.split(r"[\s　]+", (name or "").strip()) if part]
    if not parts:
        return "?.?."
    return "".join(f"{part[0]}." for part in parts)


def _pseudonym(player_id, salt):
    digest = hashlib.blake2b(
        str(player_id).encode("utf-8"), key=salt.encode("utf-8"), digest_size=8
    ).digest()
    value = int.from_bytes(digest, "big")
    label = ""
    for _ in range(4):
        label += _ALPHABET[value % len(_ALPHABET)]
        value //= len(_ALPHABET)
    return f"P-{label}"


def label(player_id, name=None, mode="full", salt=None):
    """Render one player under ``mode``."""
    if mode == "full":
        return name or str(player_id)
    if mode == "initials":
        return _initials(name)
    if mode == "pseudonym":
        if not salt:
            raise PrivacyError("pseudonym mode needs a salt; call new_salt()")
        return _pseudonym(player_id, salt)
    if mode == "aggregate":
        raise PrivacyError("aggregate mode does not emit per-player rows")
    raise PrivacyError(f"unknown privacy mode {mode!r}")


def k_anonymity(rows, quasi_identifiers):
    """How re-identifiable a table is once names are removed.

    ``k`` is the size of the smallest group sharing the same quasi-identifier
    values. ``k = 1`` means at least one row is unique on those columns and the
    person behind it can be looked up in the published squad lists, whatever
    label the name column carries.

    Args:
        rows: dicts, one per person.
        quasi_identifiers: column names an outsider could already know, e.g.
            ``["team", "position"]`` — both are on the federation's own site.

    Returns:
        ``{"k": int, "unique": int, "groups": int, "total": int}``
    """
    if not rows:
        return {"k": 0, "unique": 0, "groups": 0, "total": 0}
    signatures = Counter(
        tuple(str(row.get(column)) for column in quasi_identifiers) for row in rows
    )
    return {
        "k": min(signatures.values()),
        "unique": sum(1 for count in signatures.values() if count == 1),
        "groups": len(signatures),
        "total": len(rows),
    }


def check_public_safe(mode, rows=None, quasi_identifiers=("team", "position")):
    """Raise unless ``mode`` is fit to leave the machine.

    ``initials`` and ``full`` are rejected outright. For ``pseudonym`` the
    remaining columns are still checked, because a pseudonymous row that is
    unique on team and position is not anonymous in a twelve-team league whose
    squad lists are public.
    """
    if mode not in PUBLIC_SAFE_MODES:
        raise PrivacyError(
            f"privacy mode {mode!r} is not safe to publish; "
            f"use one of {sorted(PUBLIC_SAFE_MODES)}"
        )
    if mode == "pseudonym" and rows:
        return k_anonymity(rows, quasi_identifiers)
    return None
