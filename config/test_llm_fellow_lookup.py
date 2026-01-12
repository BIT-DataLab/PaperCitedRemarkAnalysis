import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pcra.fellow.lookup import lookup_fellow_status

CONFIG_PATH = REPO_ROOT / "config" / "llm_model.yaml"
ALLOWED_STATUSES = {"Yes", "No", "Unknown"}


def run() -> int:
    print("LLM fellow lookup test")
    if not CONFIG_PATH.exists():
        print(f"FAIL: missing config: {CONFIG_PATH}")
        return 1

    statuses, sources, error = lookup_fellow_status(
        name="Andrew Ng",
        affiliation="Stanford University",
        institutions=[{"display_name": "Stanford University"}],
        llm_config_path=CONFIG_PATH,
        max_results=2,
        timeout_s=60,
        max_retries=1,
        cache_path=None,
    )

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
