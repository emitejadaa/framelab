"""E2E: the Plotter in Chromium — drag to ▟, gallery, edits, export, formula column, delete."""

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from framelab._paths import require_static
from framelab.launch.browsers import find_chromium
from framelab.naming import RootSpec
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher
from framelab.transport.server import FramelabServer

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "frontend/tests/e2e/plot.e2e.mjs"
pytestmark = pytest.mark.slow


def _node() -> list[str] | None:
    if shutil.which("mise"):
        return ["mise", "exec", "--", "node"]
    return ["node"] if shutil.which("node") else None


@pytest.mark.skipif(find_chromium() is None, reason="no Chromium-family browser")
@pytest.mark.skipif(_node() is None, reason="node is not available")
@pytest.mark.skipif(
    not (ROOT / "frontend/node_modules/playwright-core").exists(), reason="run pnpm install"
)
def test_plotter_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rng = np.random.default_rng(0)
    ventas = pd.DataFrame(
        {
            "fecha": pd.date_range("2024-01-01", periods=80, freq="D"),
            "region": rng.choice(["Norte", "Sur", "Este"], 80),
            "monto": rng.normal(100, 25, 80).round(2),
            "cantidad": rng.integers(1, 9, 80),
        }
    )
    session = Session([RootSpec("ventas", ventas)])
    server = FramelabServer(Dispatcher(session), require_static())
    server.start()
    try:
        out = subprocess.run(
            [*_node(), str(SCRIPT), server.login_url, str(tmp_path)],
            cwd=ROOT / "frontend",
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "FRAMELAB_BROWSER": find_chromium()},
        )
        assert out.returncode == 0, out.stdout + out.stderr
        assert (tmp_path / "fig_ventas.png").read_bytes().startswith(b"\x89PNG")
        assert "ventas_2" not in session  # deleted from the UI
        [figure] = session.snapshot()["figures"]
        assert figure["kinds"] == ["scatter"] and figure["sources"] == ["n1"]
    finally:
        server.stop()
        session.close()
