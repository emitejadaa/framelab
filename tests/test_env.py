import types

import pytest

from framelab.env import Env, detect_env, resolve_mode


def shell(name):
    return type(name, (), {})()


def test_plain_script():
    assert detect_env(modules={}, environ={}, ipython=None, interactive=False) is Env.SCRIPT


def test_plain_repl():
    assert detect_env(modules={}, environ={}, ipython=None, interactive=True) is Env.REPL


def test_jupyter_kernel():
    assert detect_env(modules={}, environ={}, ipython=shell("ZMQInteractiveShell")) is Env.JUPYTER


def test_vscode_kernel():
    env = detect_env(modules={}, environ={"VSCODE_PID": "1"}, ipython=shell("ZMQInteractiveShell"))
    assert env is Env.VSCODE


def test_colab():
    mods = {"google.colab": types.ModuleType("google.colab")}
    assert detect_env(modules=mods, environ={}, ipython=shell("Shell")) is Env.COLAB


def test_spyder_kernel_has_no_widgets():
    mods = {"spyder_kernels": types.ModuleType("spyder_kernels")}
    env = detect_env(modules=mods, environ={}, ipython=shell("ZMQInteractiveShell"))
    assert env is Env.NO_WIDGETS


def test_ipython_terminal():
    env = detect_env(modules={}, environ={}, ipython=shell("TerminalInteractiveShell"))
    assert env is Env.IPYTHON_TERMINAL


def test_marimo():
    mo = types.ModuleType("marimo")
    mo.running_in_notebook = lambda: True
    assert detect_env(modules={"marimo": mo}, environ={}, ipython=None) is Env.MARIMO


def test_marimo_imported_but_not_running():
    mo = types.ModuleType("marimo")
    mo.running_in_notebook = lambda: False
    env = detect_env(modules={"marimo": mo}, environ={}, ipython=None, interactive=False)
    assert env is Env.SCRIPT


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (Env.SCRIPT, "window"),
        (Env.REPL, "window"),
        (Env.IPYTHON_TERMINAL, "window"),
        (Env.NO_WIDGETS, "window"),
        (Env.JUPYTER, "inline"),
        (Env.VSCODE, "inline"),
        (Env.COLAB, "inline"),
        (Env.MARIMO, "inline"),
    ],
)
def test_auto_mode(env, expected):
    assert resolve_mode("auto", env) == expected


def test_explicit_modes():
    assert resolve_mode("window", Env.JUPYTER) == "window"
    assert resolve_mode("inline", Env.JUPYTER) == "inline"
    with pytest.raises(ValueError, match="inline"):
        resolve_mode("inline", Env.SCRIPT)
    with pytest.raises(ValueError, match="mode"):
        resolve_mode("popup", Env.SCRIPT)
