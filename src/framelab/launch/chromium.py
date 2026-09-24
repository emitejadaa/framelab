"""Open the UI as a chromeless Chromium 'app' window with a throw-away profile."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChromiumWindow:
    process: subprocess.Popen
    profile_dir: Path

    def wait(self, timeout: float | None = None) -> int:
        code = self.process.wait(timeout)
        shutil.rmtree(self.profile_dir, ignore_errors=True)
        return code

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(5)
        shutil.rmtree(self.profile_dir, ignore_errors=True)


def build_command(
    browser: str,
    target: str,
    *,
    profile_dir: Path,
    width: int = 1400,
    height: int = 900,
    extra_args: Sequence[str] = (),
) -> list[str]:
    # A fresh --user-data-dir makes this a separate browser process: it exits exactly
    # when the window closes, and it never shows the user's tabs or profile.
    return [
        browser,
        f"--app={target}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        f"--window-size={width},{height}",
        *extra_args,
    ]


def launch_app_window(
    browser: str,
    target: str,
    *,
    width: int = 1400,
    height: int = 900,
    extra_args: Sequence[str] | None = None,
) -> ChromiumWindow:
    profile = Path(tempfile.mkdtemp(prefix="framelab-profile-"))
    extra = (
        list(extra_args)
        if extra_args is not None
        else shlex.split(os.environ.get("FRAMELAB_BROWSER_ARGS", ""))
    )
    cmd = build_command(
        browser, target, profile_dir=profile, width=width, height=height, extra_args=extra
    )
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=sys.platform != "win32",
    )
    return ChromiumWindow(process, profile)
