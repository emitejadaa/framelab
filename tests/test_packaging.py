import os
import subprocess
import sys
import tarfile
import venv
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(out), str(ROOT)], check=True)
    return out


def test_wheel_is_pure_and_contains_bundle(dist):
    (wheel,) = dist.glob("*.whl")
    assert wheel.name.endswith("-py3-none-any.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert "framelab/_static/framelab.js" in names
    assert "framelab/_static/framelab.css" in names
    assert not any("node_modules" in n for n in names)


def test_sdist_has_sources_and_bundle_but_no_node_modules(dist):
    (sdist,) = dist.glob("*.tar.gz")
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
    assert any(n.endswith("src/framelab/_static/framelab.js") for n in names)
    assert any(n.endswith("frontend/package.json") for n in names)
    assert not any("node_modules" in n for n in names)


def _path_without_node() -> str:
    keep = []
    for p in os.environ["PATH"].split(os.pathsep):
        if "mise" in p:
            continue
        if (Path(p) / "node").exists() or (Path(p) / "pnpm").exists():
            continue
        keep.append(p)
    return os.pathsep.join(keep)


def test_sdist_installs_without_node(dist, tmp_path):
    (sdist,) = dist.glob("*.tar.gz")
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    py = env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    env = {**os.environ, "PATH": _path_without_node()}
    subprocess.run(
        [str(py), "-m", "pip", "install", "-q", "--no-deps", str(sdist)], check=True, env=env
    )
    probe = (
        "import importlib.util, pathlib; spec = importlib.util.find_spec('framelab'); "
        "print((pathlib.Path(spec.origin).parent / '_static' / 'framelab.js').is_file())"
    )
    out = subprocess.run(
        [str(py), "-c", probe], check=True, env=env, capture_output=True, text=True
    )
    assert out.stdout.strip() == "True"
