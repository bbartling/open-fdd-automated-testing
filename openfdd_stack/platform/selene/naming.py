"""Canonical instance-name normalisation.

Python port of ``selenepack-smartbuildings/src/naming.rs`` (SeleneDB
schema-pack v2.0+). The convention is defined in that repo's
``docs/instance_naming.md``:

    `name` properties on instance nodes are lowercase-kebab ASCII with
    `/` as the path separator. The BAS-native label lives in a companion
    `display_name` property.

This module is pure and deterministic. Every ingest / CRUD / agent path
that writes instance names should route through :func:`canonical_name`
(or :func:`canonical_bas_path` for BAS dot-notation) so normalisation
never drifts across projects.

The Rust reference implementation is the source of truth \u2014 this file
exists only because the stack is Python. The unit tests mirror the Rust
test suite one-for-one; keep them in sync when the upstream spec changes.
"""

from __future__ import annotations

_SEGMENT_SEPARATORS = {"_", " ", "\t", ".", ":", "-"}


def canonical_name(raw: str) -> str:
    """Normalise a raw instance name to canonical kebab-lowercase form.

    Path structure is preserved: ``/`` splits the input into segments, each
    segment is canonicalised independently, and the segments are rejoined.
    Empty segments are dropped (so ``ahu-1//sat`` folds to ``ahu-1/sat``).

    Within a segment, ASCII letters are lowercased, digits are kept, and
    the common word-separator punctuation family (``_``, space, tab,
    ``.``, ``:``) is mapped to ``-``. Any other character outside
    ``[a-z0-9]`` is dropped. Runs of ``-`` are collapsed to a single
    ``-``, and leading or trailing ``-`` within a segment are stripped.

    Non-ASCII characters are dropped. Deployments with non-ASCII
    identifiers should store those in ``display_name`` and supply an
    ASCII canonical ``name`` alongside.
    """
    trimmed = raw.strip()
    segments = [_normalise_segment(seg) for seg in trimmed.split("/")]
    return "/".join(s for s in segments if s)


def canonical_bas_path(raw: str) -> str:
    """Fold a BAS-native dot-separated path to ``/`` before canonicalising.

    BAS points are conventionally addressed as ``<equipment>.<shorthand>``
    (``AHU-1.SAT``, ``VAV-203.DMPR``). The canonical form uses ``/`` as
    the separator so dashboards, URLs, and agent tool calls share one
    representation.

    Callers that need a literal dot in a name (a version slug, a decimal)
    should call :func:`canonical_name` directly, which drops dots by
    mapping them to ``-``.
    """
    return canonical_name(raw.replace(".", "/"))


def is_canonical(raw: str) -> bool:
    """True when ``raw`` is already in canonical form (a no-op round-trip).

    Useful as a post-ingest assertion or a build-time check on generator
    output.
    """
    return canonical_name(raw) == raw


def _normalise_segment(segment: str) -> str:
    """Within-segment normalisation. See :func:`canonical_name`."""
    out: list[str] = []
    last_was_hyphen = True  # strips leading hyphen
    for ch in segment:
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
            last_was_hyphen = False
        elif "A" <= ch <= "Z":
            out.append(ch.lower())
            last_was_hyphen = False
        elif ch in _SEGMENT_SEPARATORS:
            if not last_was_hyphen:
                out.append("-")
                last_was_hyphen = True
        # everything else (non-ASCII, unmapped punctuation): drop silently
    # Strip trailing hyphens.
    while out and out[-1] == "-":
        out.pop()
    return "".join(out)
