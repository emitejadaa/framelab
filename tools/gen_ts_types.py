"""Regenerate frontend/src/generated/protocol.ts from framelab.protocol.schema."""

from pathlib import Path

from framelab.protocol import schema
from framelab.protocol.tsgen import render_module

TARGET = Path(__file__).resolve().parents[1] / "frontend/src/generated/protocol.ts"

if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render_module(schema), encoding="utf-8")
    print(f"wrote {TARGET}")
