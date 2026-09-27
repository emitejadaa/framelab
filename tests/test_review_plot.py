"""Plotter regressions found by the multi-agent review."""

import datetime as dt
import decimal

import numpy as np
import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call
from framelab.plot.spec import FigureSpecError
from framelab.session import Session

SALES = pd.DataFrame(
    {
        "amount": [1.0, 5.0, 3.0, 8.0],
        "units": [1, 2, 3, 4],
        "store": ["a", "b", "a", "b"],
    }
)


@pytest.fixture
def s():
    session = Session([RootSpec("sales", SALES)])
    yield session
    session.close()


def line(source, y="amount", **extra):
    return {"kind": "line", "source": source, "y": [{"col": y}], **extra}


def with_layers(s, fid, *layers, **fields):
    spec = s.plots.get(fid)["spec"]
    spec["axes"][0]["layers"] = list(layers)
    spec.update(fields)
    return s.plots.update(fid, spec)


def test_figure_history_never_brings_back_deleted_sources(s):
    head = s.apply(call("n1", "head", n=2))
    tail = s.apply(call("n1", "tail", n=2))
    fig = s.plots.create("n1")
    with_layers(s, fig["id"], line(head.id))
    with_layers(s, fig["id"], line(tail.id))
    s.delete(head.id)
    state = s.plots.undo(fig["id"])
    sources = [ly["source"] for ly in state["spec"]["axes"][0]["layers"]]
    assert head.id not in sources
    spec = state["spec"]
    spec["axes"][0]["title"] = "still editable"
    s.plots.update(fig["id"], spec)


def test_undoing_a_delete_keeps_later_figure_edits(s):
    head = s.apply(call("n1", "head", n=2))
    fig = s.plots.create("n1")
    with_layers(s, fig["id"], line("n1"), line(head.id))
    s.delete(head.id)
    spec = s.plots.get(fig["id"])["spec"]
    spec["axes"][0]["title"] = "Quarterly report"
    spec["axes"][0]["layers"].append(
        {"kind": "scatter", "source": "n1", "x": {"col": "units"}, "y": [{"col": "amount"}]}
    )
    s.plots.update(fig["id"], spec)
    assert s.undo()
    axes = s.plots.get(fig["id"])["spec"]["axes"][0]
    assert axes["title"] == "Quarterly report"
    assert [(ly["kind"], ly["source"]) for ly in axes["layers"]] == [
        ("line", "n1"),
        ("line", head.id),
        ("scatter", "n1"),
    ]
    # the graph undo is itself undoable from the figure
    before = s.plots.undo(fig["id"])["spec"]["axes"][0]
    assert [ly["kind"] for ly in before["layers"]] == ["line", "scatter"]


def test_nodes_and_figures_share_one_namespace(s):
    s.plots.create("n1", name="sales_head")
    node = s.apply(call("n1", "head", n=2))
    assert node.name != "sales_head"
    s.plots.create("n1", name="chart")
    with pytest.raises(ValueError):
        s.apply(call("n1", "tail", n=1), name="chart")
    named = s.apply(call("n1", "tail", n=2), name="top")
    fig = s.plots.create("n1", name="to p")  # sanitizes to an existing node name
    assert (
        fig["spec"]["name"] != "top"
        and fig["spec"]["name"] != named.name
        or fig["spec"]["name"] == "to_p"
    )


def test_graph_undo_does_not_reuse_a_figure_name(s):
    head = s.apply(call("n1", "head", n=2))
    s.delete(head.id)
    s.plots.create("n1", name="sales_head")
    s.undo()
    assert s.node(head.id).name != "sales_head"


@pytest.mark.parametrize("label", [dt.date(2024, 1, 1), decimal.Decimal("1.5")])
def test_date_and_decimal_column_labels_render(label):
    frame = pd.DataFrame({label: [1.0, 2.0, 3.0]})
    session = Session([RootSpec("wide", frame)])
    try:
        fig = session.plots.create("n1")
        from framelab.ops.values import encode_scalar

        with_layers(
            session,
            fig["id"],
            {"kind": "line", "source": "n1", "y": [{"col": encode_scalar(label)}]},
        )
        png, meta = session.plots.render(fig["id"], width_px=200, height_px=150)
        assert meta["errors"] == [] and png.startswith(b"\x89PNG")
    finally:
        session.close()


def test_preview_of_split_lines_keeps_every_group():
    n = 30_000
    frame = pd.DataFrame(
        {
            "date": np.repeat(np.arange(n // 2), 2),
            "ticker": ["AAA", "BBB"] * (n // 2),
            "price": np.arange(n, dtype=float),
        }
    )
    session = Session([RootSpec("prices", frame)])
    try:
        fig = session.plots.create("n1")
        with_layers(
            session,
            fig["id"],
            {
                "kind": "line",
                "source": "n1",
                "x": {"col": "date"},
                "y": [{"col": "price"}],
                "hue": {"col": "ticker"},
            },
        )
        from framelab.plot.render import PREVIEW_ROWS, style_context

        doc = session.plots._doc(fig["id"])
        with style_context("default"):
            _, out = session.plots._build(doc, 30, PREVIEW_ROWS)
        labels = sorted(line.get_label() for line in out.figure.axes[0].get_lines())
        assert out.sampled and labels == ["AAA", "BBB"]
    finally:
        session.close()


def test_size_by_with_split_by_uses_one_scale(s):
    frame = pd.DataFrame(
        {"x": [1, 2, 3, 4], "y": [1, 2, 3, 4], "w": [10, 5, 1000, 500], "g": ["a", "a", "b", "b"]}
    )
    session = Session([RootSpec("pts", frame)])
    try:
        fig = session.plots.create("n1")
        with_layers(
            session,
            fig["id"],
            {
                "kind": "scatter",
                "source": "n1",
                "x": {"col": "x"},
                "y": [{"col": "y"}],
                "hue": {"col": "g"},
                "size_by": {"col": "w"},
            },
        )
        figure = session.plots.figure(fig["id"])
        sizes = sorted(float(v) for c in figure.axes[0].collections for v in c.get_sizes())
        assert sizes == pytest.approx([1.0, 2.0, 100.0, 200.0])
    finally:
        session.close()


def test_a_failing_layer_keeps_shared_row_selections(s):
    fig = s.plots.create("n1")
    spec = s.plots.get(fig["id"])["spec"]
    spec["ncols"] = 2
    rows = {"mode": "head", "n": 2}
    spec["axes"] = [
        {"layers": [{"kind": "heatmap", "source": "n1", "rows": rows}]},  # text column: fails
        {"layers": [line("n1", rows=rows)]},
    ]
    s.plots.update(fig["id"], spec)
    png, meta = s.plots.render(fig["id"], width_px=300, height_px=150)
    assert [(e["axes"], e["layer"]) for e in meta["errors"]] == [(0, 0)]


@pytest.mark.parametrize(
    "patch",
    [
        {"title": "net_rev_$ vs gross_rev_$"},
    ],
)
def test_drawing_errors_are_figure_errors(s, patch):
    fig = s.plots.create("n1")
    spec = s.plots.get(fig["id"])["spec"]
    spec["axes"][0]["layers"] = [line("n1")]
    spec["axes"][0].update(patch)
    s.plots.update(fig["id"], spec)
    with pytest.raises(FigureSpecError):
        s.plots.render(fig["id"], width_px=200, height_px=150)
    with pytest.raises(FigureSpecError):
        s.plots.export(fig["id"])
