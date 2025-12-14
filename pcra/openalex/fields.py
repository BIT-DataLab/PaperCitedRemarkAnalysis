"""Default select/sort field sets for OpenAlex facade APIs.

Centralizing these lets us tune payload size/performance without touching call sites.
"""

MAX_PER_PAGE = 200

DEFAULT_CITED_BY_SORT = "cited_by_count:desc,publication_year:desc"
DEFAULT_AUTHOR_WORKS_SORT = "cited_by_count:desc,publication_year:desc"

WORK_MATCH_FIELDS = [
    "id",
    "display_name",
    "title",
    "doi",
    "publication_year",
    "cited_by_count",
    "authorships",
]
WORK_MATCH_SELECT = ",".join(WORK_MATCH_FIELDS)

WORK_CITED_BY_FIELDS = [
    "id",
    "display_name",
    "title",
    "doi",
    "publication_year",
    "cited_by_count",
    "authorships",
]
WORK_CITED_BY_SELECT = ",".join(WORK_CITED_BY_FIELDS)

WORK_META_FIELDS = [
    "id",
    "display_name",
    "title",
    "doi",
    "publication_year",
    "publication_date",
    "type",
    "language",
    "ids",
    "open_access",
    "primary_location",
    "authorships",
    "cited_by_count",
    "referenced_works",
    "abstract_inverted_index",
    "topics",
]
WORK_META_SELECT = ",".join(WORK_META_FIELDS)

AUTHOR_MATCH_FIELDS = [
    "id",
    "display_name",
    "orcid",
    "ids",
    "works_count",
    "cited_by_count",
    "summary_stats",
    "last_known_institutions",
]
AUTHOR_MATCH_SELECT = ",".join(AUTHOR_MATCH_FIELDS)

AUTHOR_META_FIELDS = [
    "id",
    "display_name",
    "orcid",
    "ids",
    "works_count",
    "cited_by_count",
    "summary_stats",
    "counts_by_year",
    "last_known_institutions",
    "affiliations",
]
AUTHOR_META_SELECT = ",".join(AUTHOR_META_FIELDS)

AUTHOR_METRICS_FIELDS = [
    "id",
    "display_name",
    "summary_stats",
    "works_count",
    "cited_by_count",
]
AUTHOR_METRICS_SELECT = ",".join(AUTHOR_METRICS_FIELDS)

AUTHOR_TOP_WORKS_FIELDS = [
    "id",
    "display_name",
    "title",
    "doi",
    "publication_year",
    "cited_by_count",
    "authorships",
]
AUTHOR_TOP_WORKS_SELECT = ",".join(AUTHOR_TOP_WORKS_FIELDS)

