from __future__ import annotations

import inspect
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        import openai
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Install the tested environment first: "
            "pip install -r requirements-lock.txt"
        ) from exc

    config = json.loads(
        (ROOT / "config" / "release.json").read_text(encoding="utf-8")
    )
    signature = inspect.signature(OpenAI(api_key="interface-check").responses.parse)
    required = {"model", "input", "text_format", "reasoning", "store"}
    missing = sorted(required - set(signature.parameters))
    report = {
        "openai_version": openai.__version__,
        "configured_model": config["model"],
        "responses_parse_required_parameters": sorted(required),
        "missing_parameters": missing,
        "status": "pass" if not missing else "fail",
        "live_api_call_performed": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
