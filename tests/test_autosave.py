import os
import time

import pandas as pd
import pytest

import framelab as fl
import framelab.api as api
from framelab.naming import RootSpec
from framelab.ops.build import call
from framelab.session import Session
from framelab.session.autosave import Autosaver, latest, recent
from framelab.session.document import from_document, load

VENTAS = pd.DataFrame({"pais": ["AR", "UY"], "monto": [1.0, 2.0]})


def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS.copy())])
    yield session
    session.close()


def test_changes_are_saved_after_a_pause(s, tmp_path):
    saver = Autosaver(s, tmp_path, delay=0.05)
    try:
        head = s.apply(call("n1", "head", n=1), name="top")
        s.wait(head.id)
        assert wait_for(saver.path.exists)
        restored, problems = from_document(load(saver.path), {"ventas": VENTAS})
        assert problems == [] and restored.node(head.id).name == "top"
        restored.close()
    finally:
        saver.close()


def test_old_autosaves_are_pruned(s, tmp_path):
    for i in range(5):
        old = tmp_path / f"old{i}.framelab"
        old.write_text("{}")
        os.utime(old, (i, i))
    saver = Autosaver(s, tmp_path, delay=0.01, keep=3)
    try:
        assert saver.save() == saver.path
        assert len(list(tmp_path.glob("*.framelab"))) == 3 and saver.path.exists()
    finally:
        saver.close()


def test_autosave_failures_never_break_the_session(s, tmp_path, caplog):
    """Review focus 5: a failing save is logged, the session keeps working."""
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    saver = Autosaver(s, blocker / "sessions", delay=0.01)
    try:
        with caplog.at_level("WARNING", logger="framelab"):
            assert saver.save() is None
        assert "autosave failed" in caplog.text
        head = s.apply(call("n1", "head", n=1))
        pd.testing.assert_frame_equal(s.wait(head.id), VENTAS.head(1))
    finally:
        saver.close()


def test_recent_and_latest(s, tmp_path):
    saver = Autosaver(s, tmp_path)
    try:
        saver.save()
        [item] = recent(tmp_path)
        assert item["roots"] == ["ventas"] and item["nodes"] == 1
        assert latest(tmp_path) == saver.path
        with pytest.raises(FileNotFoundError):
            latest(tmp_path / "empty")
    finally:
        saver.close()


def test_fl_open_reopens_the_last_autosave(s, monkeypatch):
    saver = Autosaver(s)
    head = s.apply(call("n1", "head", n=1), name="top")
    s.wait(head.id)
    saver.save()
    saver.close()
    monkeypatch.setattr(api, "_show", lambda session, mode: session)
    reopened = fl.open("last", ventas=VENTAS)
    try:
        assert reopened.node("top").id == head.id
        assert reopened.autosaver is not None
        assert fl.autosaves()[0]["roots"] == ["ventas"]
    finally:
        reopened.close()
