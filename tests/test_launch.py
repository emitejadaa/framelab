import os
import tempfile
import threading
from pathlib import Path

import pytest

from framelab.launch import default_order, open_window
from framelab.launch.browser import open_in_browser
from framelab.launch.browsers import find_chromium
from framelab.launch.chromium import build_command


@pytest.fixture(autouse=True)
def no_browser_override(monkeypatch):
    monkeypatch.delenv("FRAMELAB_BROWSER", raising=False)


def test_find_chromium_linux_prefers_first_available():
    def which(name):
        return f"/usr/bin/{name}" if name == "google-chrome" else None

    assert find_chromium(platform="linux", which=which) == "/usr/bin/google-chrome"


def test_find_chromium_none_when_missing():
    assert find_chromium(platform="linux", which=lambda n: None) is None


def test_find_chromium_env_override(monkeypatch, tmp_path):
    exe = tmp_path / "mybrowser"
    exe.write_text("")
    monkeypatch.setenv("FRAMELAB_BROWSER", str(exe))
    assert find_chromium(platform="linux", which=lambda n: None) == str(exe)


def test_find_chromium_macos():
    path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    found = find_chromium(platform="darwin", which=lambda n: None, exists=lambda p: p == path)
    assert found == path


def test_command_never_contains_token(tmp_path):
    target = (tmp_path / "redirect.html").as_uri()
    cmd = build_command("/usr/bin/chromium", target, profile_dir=tmp_path / "p")
    assert cmd[0] == "/usr/bin/chromium"
    assert f"--app={target}" in cmd
    assert f"--user-data-dir={tmp_path / 'p'}" in cmd
    assert "--no-first-run" in cmd and "--no-default-browser-check" in cmd
    assert not any("token" in part for part in cmd)


def test_default_order_per_platform():
    assert default_order("linux")[0] == "chromium"
    assert default_order("win32")[0] == "pywebview"
    assert default_order("darwin")[0] == "pywebview"


class FakeServer:
    def __init__(self):
        self.ever_connected = threading.Event()
        self._idle = 0.0
        self.login_url = "http://127.0.0.1:1/?token=t"

    def write_redirect_file(self):
        fd, name = tempfile.mkstemp(suffix=".html")
        os.close(fd)
        self.last_redirect = Path(name)
        return self.last_redirect

    def idle_for(self):
        return self._idle


def test_open_in_browser_waits_for_disconnect_grace():
    server = FakeServer()
    opened = []
    ticks = {"n": 0}

    def fake_sleep(_):
        ticks["n"] += 1
        if ticks["n"] == 2:
            server.ever_connected.set()
        if ticks["n"] >= 4:
            server._idle = 100.0

    open_in_browser(server, grace=1.0, opener=opened.append, sleep=fake_sleep)
    assert opened and ticks["n"] >= 4
    # the redirect file holds the token: it must be gone once the browser is in
    assert not server.last_redirect.exists()


def test_open_in_browser_times_out_without_connection():
    server = FakeServer()
    with pytest.raises(TimeoutError):
        open_in_browser(
            server, first_connect_timeout=0.0, opener=lambda u: None, sleep=lambda s: None
        )


def test_open_window_falls_through_to_browser(monkeypatch):
    import framelab.launch as launch

    monkeypatch.setattr(launch, "find_chromium", lambda: None)
    monkeypatch.setattr(launch, "pywebview_available", lambda: False)
    monkeypatch.setattr(launch, "open_in_browser", lambda server: None)
    assert open_window(FakeServer(), order=("chromium", "pywebview", "browser")) == "browser"


def test_open_window_raises_when_everything_fails(monkeypatch):
    import framelab.launch as launch

    monkeypatch.setattr(launch, "find_chromium", lambda: None)
    monkeypatch.setattr(launch, "pywebview_available", lambda: False)

    def boom(server):
        raise OSError("no display")

    monkeypatch.setattr(launch, "open_in_browser", boom)
    with pytest.raises(RuntimeError, match="no display"):
        open_window(FakeServer())


def test_open_window_rejects_browser_that_never_connects(monkeypatch):
    import framelab.launch as launch

    class Window:
        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(launch, "find_chromium", lambda: "/usr/bin/chromium")
    monkeypatch.setattr(launch, "launch_app_window", lambda browser, target: Window())
    monkeypatch.setattr(launch, "pywebview_available", lambda: False)
    monkeypatch.setattr(launch, "open_in_browser", lambda server: None)
    assert open_window(FakeServer(), order=("chromium", "browser")) == "browser"
