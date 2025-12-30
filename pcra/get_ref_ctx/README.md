# `pcra.get_ref_ctx`

Module 5: extract in-text citation contexts for a referenced paper from extracted PDF text.

## What it does

Given extracted paper text (Markdown from `pymupdf4llm` or plain text from PyMuPDF) and a target
paper title:

1. Locate the last `References` / `Bibliography` heading line.
2. Parse reference entries, including numbered entries like `[id]` and unnumbered author-year
   entries (fallback splitting by blank lines / year anchors / list items).
3. Match the target title to a reference entry to get its `ref_id` and (if available)
   author-year key (first-author surname + year suffix like `2021a`).
4. Search the body for either numeric citation brackets (`[id]`, `[id1, id2]`, `[id1–id2]`) or
   author-year citations like `(Wu et al. 2021a)` / `Wu et al. (2021a)`.
5. Extract +/- `window` characters as contexts for each in-text match.

## API

```python
from pcra.get_ref_ctx import get_paper_reference_context

result = get_paper_reference_context(
    md_text,
    "Attention Is All You Need",
    window=512,
    match_threshold=0.8,
    citation_style="auto",  # auto | numeric | author_year
)
```

If the References heading cannot be found, the facade returns an empty result with an `error` field
and logs a warning.
