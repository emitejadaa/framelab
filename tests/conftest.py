import pytest


@pytest.fixture(autouse=True)
def _framelab_data_dir(tmp_path_factory, monkeypatch):
    """Autosaves from tests never land in the real user data folder."""
    monkeypatch.setenv("FRAMELAB_DATA_DIR", str(tmp_path_factory.mktemp("framelab-data")))
