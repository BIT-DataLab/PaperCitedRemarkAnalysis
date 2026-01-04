"""Author enrichment helpers."""

from .metrics import collect_author_ids_from_works, compute_max_h_index_author, enrich_authors_with_metrics

__all__ = [
    "collect_author_ids_from_works",
    "compute_max_h_index_author",
    "enrich_authors_with_metrics",
]
