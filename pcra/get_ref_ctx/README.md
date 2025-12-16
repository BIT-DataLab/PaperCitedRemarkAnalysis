# `pcra.get_ref_ctx`

Module 5: extract in-text citation contexts for a referenced paper from extracted PDF text.

## What it does

Given extracted paper text (Markdown from `pymupdf4llm` or plain text from PyMuPDF) and a target
paper title:

1. Locate the last `References` / `Bibliography` heading line.
2. Parse numbered reference entries that start with `[id]`.
3. Match the target title to a reference entry to get its numeric `ref_id`.
4. Search the body for citation brackets like `[id]` or `[id1, id2, ...]`.
5. Extract +/- `window` characters as contexts for each in-text match.

## API

```python
from pcra.get_ref_ctx import get_paper_reference_context

result = get_paper_reference_context(md_text, "Attention Is All You Need", window=512, match_threshold=0.8)
```

If the References heading cannot be found, the facade returns an empty result with an `error` field
and logs a warning.

