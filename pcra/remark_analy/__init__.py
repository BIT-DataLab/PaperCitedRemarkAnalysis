"""LLM-based citation remark analysis utilities."""

from .batch import score_paper_contexts
from .config import LLMConfig, load_llm_config
from .report import (
    build_paper_summary,
    build_cited_paper_remarks,
    render_paper_report,
    render_summary_report,
    render_summary_report_v2,
    write_paper_report,
    write_summary_report,
    write_summary_report_v2,
)
from .scorer import PROMPT_VERSION, score_context

__all__ = [
    "LLMConfig",
    "PROMPT_VERSION",
    "build_paper_summary",
    "build_cited_paper_remarks",
    "load_llm_config",
    "render_paper_report",
    "render_summary_report",
    "render_summary_report_v2",
    "score_context",
    "score_paper_contexts",
    "write_paper_report",
    "write_summary_report",
    "write_summary_report_v2",
]
