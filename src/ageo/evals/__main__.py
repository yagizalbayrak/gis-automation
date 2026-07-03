"""CLI entry point: uv run python -m ageo.evals [--no-llm] [--only S05 ...]"""
from __future__ import annotations

import argparse
from datetime import datetime

from ageo.evals.harness import run_pool


def main() -> None:
    parser = argparse.ArgumentParser(description="ageo scenario evaluation")
    parser.add_argument("--no-llm", action="store_true",
                        help="deterministic planner only (no composer calls)")
    parser.add_argument("--only", nargs="*", default=None,
                        help="run only these scenario ids")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=None,
                        help="results JSON path (default: evals_results/<ts>.json)")
    args = parser.parse_args()

    out = args.out or f"evals_results/{datetime.now():%Y%m%d_%H%M%S}.json"
    run_pool(
        use_llm=not args.no_llm,
        only=args.only,
        limit=args.limit,
        out_path=out,
    )


if __name__ == "__main__":
    main()
