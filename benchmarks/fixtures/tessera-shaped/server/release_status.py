from pathlib import Path


STATE_PATH = Path(__file__).resolve().parents[1] / "runtime" / "release-state.json"


def read_status() -> dict[str, str]:
    return {
        "releaseId": "unknown",
        "status": "unknown",
        "reason": "not_wired",
        "provider": "fixture-mail",
        "updatedAt": "2026-08-13T00:00:00Z",
    }