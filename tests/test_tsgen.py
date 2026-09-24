import sys
import types
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from framelab.protocol import schema
from framelab.protocol.tsgen import render_module

ROOT = Path(__file__).resolve().parents[1]


def test_render_small_module():
    mod = types.ModuleType("fake_schema")
    Color = Literal["red", "blue"]

    class Item(TypedDict):
        name: str
        size: int
        tags: list[str]
        color: Color
        meta: dict[str, Any]
        note: NotRequired[str | None]

    Item.__module__ = "fake_schema"
    mod.LIMIT = 3
    mod.Color = Color
    mod.Item = Item
    sys.modules["fake_schema"] = mod
    try:
        out = render_module(mod)
    finally:
        del sys.modules["fake_schema"]
    assert "export const LIMIT = 3 as const;" in out
    assert 'export type Color = "red" | "blue";' in out
    assert "export interface Item {" in out
    assert "  name: string;" in out
    assert "  size: number;" in out
    assert "  tags: string[];" in out
    assert "  color: Color;" in out
    assert "  meta: Record<string, unknown>;" in out
    assert "  note?: string | null;" in out


def test_generated_file_is_up_to_date():
    generated = (ROOT / "frontend/src/generated/protocol.ts").read_text(encoding="utf-8")
    assert generated == render_module(schema), "run: .venv/bin/python tools/gen_ts_types.py"
