"""OpenAlex helpers (id normalization, abstract decoding, small pure utilities)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, TypeVar, Union

T = TypeVar("T")


def to_short_openalex_id(value: Optional[str]) -> Optional[str]:
    """Normalize an OpenAlex entity id into short form (e.g. 'W123', 'A123')."""
    if not value:
        return None
    value = value.strip()
    if value.startswith(("http://", "https://")):
        return value.rstrip("/").split("/")[-1]
    return value


def join_fields(fields: Optional[Union[str, Sequence[str]]]) -> Optional[str]:
    if fields is None:
        return None
    if isinstance(fields, str):
        return fields
    return ",".join(fields)


def dedupe_preserve_order(items: Iterable[T]) -> List[T]:
    seen = set()
    out: List[T] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def decode_abstract_inverted_index(work: Dict[str, Any]) -> Optional[str]:
    """Decode OpenAlex abstract_inverted_index into a plain text abstract string."""
    abstract_inverted = work.get("abstract_inverted_index")
    if not abstract_inverted or not isinstance(abstract_inverted, dict):
        return None
    tokens = []
    for word, positions in abstract_inverted.items():
        for pos in positions or []:
            tokens.append((pos, word))
    tokens.sort(key=lambda x: x[0])
    return " ".join(w for _, w in tokens) if tokens else None

