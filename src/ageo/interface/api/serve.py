"""Development server entry point.

    uv run python -m ageo.interface.api.serve          # real OSM gateway
    uv run python -m ageo.interface.api.serve --demo   # offline synthetic Kutahya

Demo mode (also enabled by AGEO_DEMO=1) swaps in the deterministic demo
OSM gateway so the full workbench can be shown without network access.
"""
from __future__ import annotations

import argparse
import os

import uvicorn

from ageo.interface.api.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="ageo dev server")
    parser.add_argument("--demo", action="store_true",
                        help="use the offline synthetic Kutahya OSM gateway")
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", "8000"))
    )
    args = parser.parse_args()

    gateway = None
    composer_llm = None
    if args.demo or os.environ.get("AGEO_DEMO") == "1":
        from ageo.infrastructure.gis.demo import DemoComposerLlm, DemoOsmGateway

        gateway = DemoOsmGateway()
        composer_llm = DemoComposerLlm()
    uvicorn.run(
        create_app(osm_gateway=gateway, composer_llm=composer_llm),
        host=os.environ.get("AGEO_HOST", "127.0.0.1"),
        port=args.port,
    )


if __name__ == "__main__":
    main()
