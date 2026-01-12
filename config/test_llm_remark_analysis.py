import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pcra.remark_analy import load_llm_config
from pcra.remark_analy.scorer import score_context

CONFIG_PATH = REPO_ROOT / "config" / "llm_model.yaml"


def run() -> int:
    print("LLM remark analysis test")
    if not CONFIG_PATH.exists():
        print(f"FAIL: missing config: {CONFIG_PATH}")
        return 1

    try:
        config = load_llm_config(CONFIG_PATH)
    except Exception as exc:
        print(f"FAIL: load config error: {type(exc).__name__}: {exc}")
        return 1

    payload = {
        "target_title": "CrowdChart: Crowdsourced Data Extraction from Visualization Charts",
        "reference_entry": "A. Author et al. CrowdChart.",
        "citation_marker": "[12]",
        "citing_paper_title": "Example Paper",
        "context": (
            "We build on the CrowdChart approach to extract chart data, "
            "showing improved accuracy over prior baselines."
        ),
    }

    try:
        result = score_context(payload, config=config, dry_run=False)
    except Exception as exc:
        print(f"FAIL: LLM call error: {type(exc).__name__}: {exc}")
        return 1

    print(f"remark_score: {result.remark_score}")
    print(f"reason: {result.reason}")
    if result.error:
        print(f"error: {result.error}")

    ok = result.error is None and isinstance(result.remark_score, int) and 0 <= result.remark_score <= 10
    ok = ok and bool(result.reason.strip())
    if ok:
        print("PASS")
        return 0
    print("FAIL: invalid result")
    return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
