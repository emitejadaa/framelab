"""Hatch build hook: build the frontend bundle when it is missing."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if os.environ.get("FRAMELAB_SKIP_JS") == "1":
            return
        root = Path(self.root)
        bundle = root / "src" / "framelab" / "_static" / "framelab.js"
        if bundle.is_file() and os.environ.get("FRAMELAB_FORCE_JS") != "1":
            return
        frontend = root / "frontend"
        if not (frontend / "package.json").is_file():
            raise RuntimeError(
                "framelab: the frontend bundle is missing and frontend/ sources are not available"
            )
        pnpm = self._pnpm()
        subprocess.run([*pnpm, "install", "--frozen-lockfile"], cwd=frontend, check=True)
        subprocess.run([*pnpm, "run", "build"], cwd=frontend, check=True)
        if not bundle.is_file():
            raise RuntimeError("framelab: the frontend build finished but framelab.js is missing")

    @staticmethod
    def _pnpm() -> list[str]:
        if shutil.which("mise"):
            return ["mise", "exec", "--", "pnpm"]
        if shutil.which("pnpm"):
            return ["pnpm"]
        raise RuntimeError(
            "framelab: pnpm is required to build the frontend (run `mise install`), "
            "or set FRAMELAB_SKIP_JS=1 to skip it"
        )
