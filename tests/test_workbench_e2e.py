"""E2E #2/#3: the real bundle in Chromium — right-click an op, see code, open the table."""

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
SCRIPT = ROOT / "frontend/tests/e2e/workbench.e2e.mjs"
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
def test_right_click_head_code_and_table(tmp_path):
    rng = np.random.default_rng(0)
    ventas = pd.DataFrame(
        {"pais": rng.choice(["AR", "UY"], 20), "monto": rng.random(20) * 100, "n": range(20)}
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
            timeout=120,
            env={**__import__("os").environ, "FRAMELAB_BROWSER": find_chromium()},
        )
        assert out.returncode == 0, out.stdout + out.stderr
        assert "ventas_head" in session
        pd.testing.assert_frame_equal(session["ventas_head"], ventas.head(3))
    finally:
        server.stop()
        session.close()
