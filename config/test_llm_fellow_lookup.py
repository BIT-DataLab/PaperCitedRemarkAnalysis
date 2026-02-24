import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pcra.fellow.lookup import lookup_fellow_status

CONFIG_PATH = REPO_ROOT / "config" / "llm_model.yaml"
DEBUG_DIR = REPO_ROOT / "log" / "fellow_lookup_test"
ALLOWED_STATUSES = {"Yes", "No", "Unknown"}


def _latest_debug_file(debug_dir: Path) -> Path | None:
    if not debug_dir.exists():
        return None
    files = [p for p in debug_dir.glob("*.json") if p.is_file()]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def _print_debug_summary(debug_path: Path) -> None:
    try:
        payload = json.loads(debug_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"debug_summary_error: {type(exc).__name__}: {exc}")
        return

    local = payload.get("local") or {}
    search = local.get("search") or {}
    selected = search.get("candidates_selected") or []
    processed = local.get("candidates_processed") or []
    rule_matches = local.get("rule_matches") or []
    result = payload.get("result") or {}
    result_statuses = result.get("statuses") or {}
    result_sources = result.get("sources") or []

    print(
        "debug_search: "
        f"raw={search.get('search_results_raw_count', 0)} "
        f"selected={len(selected)} processed={len(processed)}"
    )
    if selected:
        print("debug_selected_candidates:")
        for idx, item in enumerate(selected, start=1):
            print(f"  - #{idx} {item.get('url')} (score={item.get('score')})")

    selected_extractors = []
    for item in processed:
        p1 = item.get("phase1_selected_extractor")
        p2 = item.get("phase2_selected_extractor")
        if p1:
            selected_extractors.append({"url": item.get("url"), "phase": "phase1", "extractor": p1})
        if p2:
            selected_extractors.append({"url": item.get("url"), "phase": "phase2", "extractor": p2})
    print(f"debug_selected_extractors: {len(selected_extractors)}")
    for ext in selected_extractors:
        print(f"  - {ext['phase']} {ext['extractor']} @ {ext['url']}")

    print(f"debug_rule_matches: {len(rule_matches)}")
    for rm in rule_matches[:5]:
        match = rm.get("match") or {}
        print(
            "  - "
            f"{rm.get('phase')} {rm.get('url')} "
            f"{match.get('orgs')} text={match.get('matched_text')!r}"
        )

    print(f"debug_result_sources: {result_sources}")
    if all(result_statuses.get(k) == "Unknown" for k in ("ieee", "acm", "aaai")):
        reason = "llm_unknown"
        if int(search.get("search_results_raw_count", 0)) == 0 and not processed:
            reason = "no_candidates"
        elif processed and all(
            int(item.get("phase1_markdown_chars") or 0) == 0
            and int(item.get("phase2_markdown_chars") or 0) == 0
            for item in processed
        ):
            reason = "extraction_empty"
        elif not rule_matches:
            reason = "rule_not_matched_or_llm_unknown"
        print(f"debug_unknown_reason: {reason}")


def run() -> int:
    print("LLM fellow lookup test")
    if not CONFIG_PATH.exists():
        print(f"FAIL: missing config: {CONFIG_PATH}")
        return 1

    statuses, sources, error = lookup_fellow_status(
        name="lizhen cui" , # "Guoliang Li", "Cyrus Shahabi" 
        affiliation="shandong university" , # "Tsinghua University", "University of Southern California"
        institutions=[{"display_name": "shandong university"}],
        llm_config_path=CONFIG_PATH,
        max_results=5,
        timeout_s=60,
        max_retries=1,
        cache_path=None,
        debug_dir=DEBUG_DIR,
    )

    print(f"debug_dir: {DEBUG_DIR}")
    latest_debug = _latest_debug_file(DEBUG_DIR)
    if latest_debug:
        print(f"latest_debug_file: {latest_debug}")
        _print_debug_summary(latest_debug)

    if error:
        print(f"FAIL: LLM error: {error}")
        return 1

    print(f"statuses: {statuses}")
    print(f"sources_count: {len(sources)}")
    if sources:
        print(f"source_1: {sources[0]}")

    ok = isinstance(statuses, dict)
    for key in ("ieee", "acm", "aaai"):
        value = statuses.get(key)
        if value not in ALLOWED_STATUSES:
            ok = False
            print(f"invalid status for {key}: {value}")
    if ok:
        print("PASS")
        return 0
    print("FAIL: invalid result")
    return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
