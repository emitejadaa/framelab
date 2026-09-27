"""Protocol, CLI and table regressions found by the multi-agent review."""

import pandas as pd
import pytest

import framelab.api as api
from framelab.__main__ import main
from framelab.errors import BadRequest
from framelab.naming import RootSpec
from framelab.ops import Op
from framelab.ops.build import call
from framelab.session import Session
from framelab.table import summarize
from framelab.transport.dispatcher import Dispatcher


@pytest.fixture
def opened(monkeypatch):
    sessions = []

    def show(session, mode):
        sessions.append(session)
        return session

    monkeypatch.setattr(api, "_show", show)
    monkeypatch.setattr(api, "_start_autosave", lambda session: None)
    yield sessions
    for s in sessions:
        s.close()


@pytest.mark.parametrize("stem", ["name", "mode"])
def test_cli_opens_files_named_like_explore_parameters(tmp_path, opened, stem):
    pd.DataFrame({"a": [1]}).to_csv(tmp_path / f"{stem}.csv", index=False)
    assert main([str(tmp_path / f"{stem}.csv")]) == 0
    assert opened[0].names == [stem]


def test_cli_keeps_files_whose_names_clean_up_the_same(tmp_path, opened):
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        pd.DataFrame({"a": [1]}).to_csv(tmp_path / folder / "sales.csv", index=False)
    (tmp_path / "data-1.csv").write_text("a\n1\n")
    (tmp_path / "data_1.csv").write_text("a\n2\n")
    files = [
        tmp_path / "a" / "sales.csv",
        tmp_path / "b" / "sales.csv",
        tmp_path / "data-1.csv",
        tmp_path / "data_1.csv",
    ]
    main([str(f) for f in files])
    assert opened[0].names == ["sales", "sales_2", "data_1", "data_1_2"]


FRAME = pd.DataFrame(
    {
        "t": pd.date_range("2020", periods=4),
        "g": [1, 1, 2, 2],
        "a": [1.0, 2, 3, 4],
        "b": [5.0, 6, 7, 8],
    }
)


def texts(obj):
    return [c["text"] for c in summarize(obj)["columns"]]


def test_summary_follows_the_groupby_column_selection():
    assert texts(FRAME.groupby("g")[["a"]]) == ["a"]
    assert texts(FRAME.groupby("g")) == ["t", "a", "b"]


def test_summary_follows_the_window_column_selection():
    assert texts(FRAME.rolling(2)[["a"]]) == ["a"]


def test_summary_keeps_repeated_labels_once_each():
    frame = pd.DataFrame([[1, 2, 3]], columns=["a", "a", "g"])
    assert texts(frame.groupby("g")) == ["a", "a"]


@pytest.fixture
def s():
    session = Session([RootSpec("df", pd.DataFrame({"a": [1, 2, 1], "b": ["x", "y", "x"]}))])
    yield session
    session.close()


@pytest.mark.parametrize("attr", ["index", "columns"])
def test_cell_filters_on_an_index_node(s, attr):
    idx = s.apply(Op("attr", "n1", name=attr))
    s.wait(idx.id, 5)
    node = s.filter_cell(idx.id, 1, 0)
    value = s.wait(node.id, 5)
    assert list(value) == [list(s.wait(idx.id))[1]]


def test_cell_filters_refuse_a_multiindex(s):
    grouped = s.apply(call("n1", "set_index", ["a", "b"]))
    idx = s.apply(Op("attr", grouped.id, name="index"))
    s.wait(idx.id, 5)
    with pytest.raises(BadRequest):
        s.filter_cell(idx.id, 0, 0)


def req(d, method, params):
    env, _ = d.handle({"v": 1, "id": "c1", "type": "req", "method": method, "params": params}, [])
    return env


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("node.window", {"id": "n1", "limit": None, "offset": None}),
        ("node.summary", None),
    ],
)
def test_missing_or_null_params_use_the_defaults(s, method, params):
    env = req(Dispatcher(s), method, params if params is not None else {"id": "n1"})
    assert "error" not in env
    if params is None:
        assert req(Dispatcher(s), method, None)["error"]["code"] == "bad_request"


def test_params_must_be_an_object(s):
    assert req(Dispatcher(s), "node.summary", [1, 2])["error"]["code"] == "bad_request"


@pytest.mark.parametrize("method", ["node.apply", "op.preview"])
def test_names_must_be_text_and_free(s, method):
    op = {"schema_v": 1, "kind": "call", "target": "n1", "name": "head", "args": [], "kwargs": {}}
    d = Dispatcher(s)
    assert req(d, method, {"op": op, "name": 5})["error"]["code"] == "bad_request"
    assert req(d, method, {"op": op, "name": "df"})["error"]["code"] == "name_taken"
