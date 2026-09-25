import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
from matplotlib.testing.compare import compare_images

from framelab.naming import RootSpec
from framelab.ops.build import call
from framelab.plot.codegen import _Gen
from framelab.plot.kinds import KINDS, catalog
from framelab.plot.render import PlotCodeError, validate_plot_code
from framelab.plot.spec import FigureSpecError, normalize
from framelab.session import Session

PNG = b"\x89PNG\r\n\x1a\n"


# ruff: noqa: E501 - the gallery below reads best one layer per line


def col(name):
    return {"col": name}


@pytest.fixture
def ventas():
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "fecha": pd.date_range("2024-01-01", periods=60, freq="D"),
            "region": rng.choice(["Norte", "Sur", "Este"], 60),
            "monto": rng.normal(100, 20, 60).round(2),
            "cantidad": rng.integers(1, 10, 60),
        }
    )


@pytest.fixture
def session(ventas):
    s = Session([RootSpec("ventas", ventas)])
    yield s
    s.close()


def figure_with(session, *layers, **fields):
    fig = session.plots.create("n1")
    spec = {**fig["spec"], **fields}
    spec["axes"][0]["layers"] = list(layers)
    return session.plots.update(fig["id"], spec)


# fmt: off
GALLERY = {
    "line": {"kind": "line", "source": "n1", "x": col("fecha"), "y": [col("monto")], "hue": col("region")},
    "line_many": {"kind": "line", "source": "n1", "y": [col("monto"), col("cantidad")], "props": {"marker": "o"}},
    "scatter": {
        "kind": "scatter", "source": "n1", "x": col("cantidad"), "y": [col("monto")],
        "color_by": col("cantidad"), "size_by": col("monto"), "props": {"cmap": "plasma"},
    },
    "bar": {"kind": "bar", "source": "totals", "props": {"color": "#3b82f6"}},
    "grouped_bar": {"kind": "bar", "source": "n1", "rows": {"mode": "head", "n": 5},
                    "x": col("fecha"), "y": [col("monto"), col("cantidad")]},
    "barh": {"kind": "barh", "source": "totals"},
    "hist": {"kind": "hist", "source": "n1", "y": [col("monto")], "hue": col("region"),
             "props": {"bins": 15, "stacked": True}},
    "box": {"kind": "box", "source": "n1", "y": [col("monto")], "hue": col("region")},
    "violin": {"kind": "violin", "source": "n1", "y": [col("monto"), col("cantidad")]},
    "pie": {"kind": "pie", "source": "totals", "props": {"autopct": True}},
    "area": {"kind": "area", "source": "n1", "x": col("fecha"), "y": [col("monto"), col("cantidad")]},
    "step": {"kind": "step", "source": "n1", "x": col("fecha"), "y": [col("monto")],
             "rows": {"mode": "filter", "column": col("region"), "op": "==", "value": "Norte"}},
    "hexbin": {"kind": "hexbin", "source": "n1", "x": col("cantidad"), "y": [col("monto")],
               "props": {"gridsize": 10}},
    "heatmap": {"kind": "heatmap", "source": "n1", "y": [col("monto"), col("cantidad")],
                "rows": {"mode": "head", "n": 10}},
}
# fmt: on


def test_catalog_kinds_all_have_a_generator():
    for key, kind in KINDS.items():
        assert hasattr(_Gen, f"_{key}"), key
        for prop in kind.props:
            if prop.type == "choice":
                assert prop.default in prop.choices, (key, prop.key)
    described = catalog()
    assert [k["key"] for k in described["kinds"]] == list(KINDS)
    assert described["styles"][0] == "default" and "ggplot" in described["styles"]


@pytest.mark.parametrize("name", list(GALLERY))
def test_every_kind_renders_without_layer_errors(session, name):
    grouped = session.apply(call("n1", "groupby", by="region"))
    totals = session.apply(call(grouped.id, "sum", numeric_only=True))
    series = session.apply(call(totals.id, "sum", axis=1))  # a Series indexed by region
    layer = dict(GALLERY[name])
    if layer["source"] == "totals":
        layer["source"] = series.id
    fig = figure_with(session, layer)
    png, meta = session.plots.render(fig["id"], width_px=500, height_px=320)
    assert png.startswith(PNG) and meta["errors"] == [], meta
    assert 0 < meta["width"] <= 500 and 0 < meta["height"] <= 320
    code = session.plots.code(fig["id"])
    assert code.startswith("import matplotlib.pyplot as plt") and code.rstrip().endswith(
        "plt.show()"
    )


def test_code_uses_the_users_names_and_matplotlib_oo(session):
    fig = figure_with(session, GALLERY["line"], name="fig_ventas")
    fig["spec"]["axes"][0]["title"] = "Ventas por región"
    session.plots.update(fig["id"], fig["spec"])
    assert session.plots.code(fig["id"], mode="figure") == (
        'fig_ventas, ax_ventas = plt.subplots(figsize=(8, 5), layout="constrained")\n'
        'for key, group in ventas.groupby("region"):\n'
        '    ax_ventas.plot(group["fecha"], group["monto"], label=key)\n'
        'ax_ventas.set_title("Ventas por región")\n'
        'ax_ventas.set_xlabel("fecha")\n'
        'ax_ventas.set_ylabel("monto")\n'
        'ax_ventas.legend(title="region")'
    )


def test_full_code_includes_the_source_pipeline(session):
    head = session.apply(call("n1", "head", n=10))
    fig = session.plots.create(head.id)
    spec = fig["spec"]
    spec["axes"][0]["layers"] = [
        {"kind": "bar", "source": head.id, "x": col("fecha"), "y": [col("monto")]}
    ]
    session.plots.update(fig["id"], spec)
    code = session.plots.code(fig["id"])
    assert "# ventas: the DataFrame (60 × 4) passed to fl.explore()" in code
    assert "ventas_head = ventas.head(n=10)" in code
    assert "fig_ventas_head, ax_ventas_head = plt.subplots(" in code
    assert 'ax_ventas_head.bar(ventas_head["fecha"], ventas_head["monto"])' in code


def test_grids_styles_and_limits(session):
    fig = session.plots.create("n1")
    spec = {
        **fig["spec"],
        "nrows": 2,
        "ncols": 2,
        "sharex": True,
        "style": "ggplot",
        "suptitle": "Resumen",
    }
    spec["axes"] = [
        {"layers": [GALLERY["hist"]], "xlim": [50, None], "grid": True, "yscale": "log"},
        None,
        None,
        {"layers": [GALLERY["scatter"]], "xrotation": 45, "legend": "upper left", "xlabel": ""},
    ]
    state = session.plots.update(fig["id"], spec)
    assert len(state["spec"]["axes"]) == 4
    code = session.plots.code(fig["id"], mode="figure")
    assert code.startswith(
        'with plt.style.context("ggplot"):\n    fig_ventas, axs_ventas = plt.subplots(2, 2, '
    )
    assert "sharex=True" in code
    assert "    axs_ventas[0, 0].set_xlim(left=50)" in code
    assert '    axs_ventas[0, 0].set_yscale("log")' in code
    assert '    axs_ventas[1, 1].tick_params(axis="x", labelrotation=45)' in code
    assert '    axs_ventas[1, 1].legend(loc="upper left")' in code
    assert "set_xlabel" not in code.split("axs_ventas[1, 1]", 1)[1]  # "" means no label
    assert '    fig_ventas.suptitle("Resumen")' in code
    png, meta = session.plots.render(fig["id"], width_px=600, height_px=400)
    assert png.startswith(PNG) and meta["errors"] == []


def test_filter_values_become_literals(session):
    layer = {"kind": "line", "source": "n1", "x": col("fecha"), "y": [col("monto")],
             "rows": {"mode": "filter", "column": col("fecha"), "op": ">=",
                      "value": {"$": "ts", "iso": "2024-02-01T00:00:00", "tz": None}}}  # fmt: skip
    fig = figure_with(session, layer)
    code = session.plots.code(fig["id"])
    assert 'ventas_plot = ventas[ventas["fecha"] >= pd.Timestamp("2024-02-01T00:00:00")]' in code
    _, meta = session.plots.render(fig["id"], width_px=400, height_px=300)
    assert meta["errors"] == []


def test_a_broken_layer_does_not_hide_the_others(session):
    bad = {"kind": "line", "source": "n1", "y": [col("no_existe")]}
    also_bad = {"kind": "hexbin", "source": "n1", "x": col("region"), "y": [col("monto")]}
    fig = figure_with(session, GALLERY["line_many"], bad, also_bad)
    png, meta = session.plots.render(fig["id"], width_px=400, height_px=300)
    assert png.startswith(PNG)
    assert [(e["axes"], e["layer"]) for e in meta["errors"]] == [(0, 1), (0, 2)]
    assert "no_existe" in meta["errors"][0]["message"]
    assert "# layer skipped: y: there is no column 'no_existe'" in session.plots.code(fig["id"])
    with pytest.raises(FigureSpecError):
        session.plots.export(fig["id"])


def test_preview_samples_big_sources_but_exports_everything():
    big = pd.DataFrame({"x": np.arange(50_000.0), "y": np.sin(np.arange(50_000.0))})
    session = Session([RootSpec("big", big)])
    try:
        fig = figure_with(
            session, {"kind": "scatter", "source": "n1", "x": col("x"), "y": [col("y")]}
        )
        _, meta = session.plots.render(fig["id"], width_px=300, height_px=200)
        assert meta["sampled"] is True
        full = session.plots.figure(fig["id"])
        assert len(full.axes[0].collections[0].get_offsets()) == 50_000
        assert "_preview" not in session.plots.code(fig["id"])
    finally:
        session.close()


def test_undo_redo_and_names(session):
    fig = session.plots.create("n1")
    assert fig["spec"]["name"] == "fig_ventas" and fig["suggestions"]
    second = session.plots.create("n1")
    assert second["spec"]["name"] == "fig_ventas_2"
    spec = fig["spec"]
    spec["axes"][0]["title"] = "uno"
    session.plots.update(fig["id"], spec)
    spec["axes"][0]["title"] = "dos"
    state = session.plots.update(fig["id"], spec)
    assert state["can_undo"] and not state["can_redo"]
    assert session.plots.undo(fig["id"])["spec"]["axes"][0]["title"] == "uno"
    assert session.plots.redo(fig["id"])["spec"]["axes"][0]["title"] == "dos"
    with pytest.raises(FigureSpecError):
        session.plots.update(fig["id"], {**spec, "name": "fig_ventas_2"})
    with pytest.raises(FigureSpecError):
        session.plots.update(fig["id"], {**spec, "name": "ventas"})  # a node's name
    assert [f["name"] for f in session.snapshot()["figures"]] == ["fig_ventas", "fig_ventas_2"]
    session.plots.delete(second["id"])
    assert [f["id"] for f in session.snapshot()["figures"]] == [fig["id"]]
    assert set(session.figures) == {"fig_ventas"}


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"kind": "radar"}, "kind"),
        ({"source": "n99"}, "unknown node"),
        ({"props": {"color": "notacolor"}}, "color"),
        ({"props": {"linewidth": 99}}, "between"),
        ({"props": {"bins": 3}}, "no property"),
        (
            {
                "hue": col("region"),
                "color_by": col("cantidad"),
                "kind": "scatter",
                "x": col("cantidad"),
            },
            "either",
        ),
        ({"rows": {"mode": "filter", "column": None}}, "filter on"),
        ({"rows": {"mode": "head", "n": 0}}, "between"),
        ({"x": {"col": {"$": "bogus"}}}, "invalid column"),
        ({"x": "fecha"}, "column, the index"),
    ],
)
def test_invalid_specs_are_rejected(patch, message):
    layer = {"kind": "line", "source": "n1", "y": [col("monto")], **patch}
    with pytest.raises(FigureSpecError, match=message):
        normalize({"name": "f", "axes": [{"layers": [layer]}]}, {"n1"})


def test_spec_limits():
    with pytest.raises(FigureSpecError):
        normalize({"name": "f", "nrows": 5}, set())
    with pytest.raises(FigureSpecError):
        normalize({"name": "f", "style": "../../etc"}, set())
    with pytest.raises(FigureSpecError):
        normalize({"name": "f", "axes": [{"title": "x" * 1000}]}, set())
    assert normalize({"name": "1 fig!"}, set())["name"] == "df_1_fig"


@pytest.mark.parametrize(
    "code",
    [
        'fig.savefig("/tmp/x.png")',
        "import os",
        "ax.figure.savefig('x')",
        "ventas.to_csv('x')",
        "ventas.__class__",
        "open('x')",
        "fig.canvas.draw()",
        "ax.set_title(ventas.pipe(print))",
        "ventas = 1",
    ],
)
def test_figure_code_validator_blocks_side_effects(code):
    with pytest.raises(PlotCodeError):
        validate_plot_code(code, {"ventas", "pd", "np", "Figure", "str"}, "fig", "ax")


def test_export_writes_the_file_and_the_code_mentions_it(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fig = figure_with(session, GALLERY["line"])
    data, meta = session.plots.export(fig["id"], fmt="png", dpi=80, path="salida.png")
    assert (tmp_path / "salida.png").read_bytes() == data and data.startswith(PNG)
    assert meta["path"] == str(tmp_path / "salida.png")
    assert 'fig_ventas.savefig("salida.png", dpi=80)' in session.plots.code(fig["id"])
    svg, _ = session.plots.export(fig["id"], fmt="svg")
    assert b"<svg" in svg[:500]
    pdf, _ = session.plots.export(fig["id"], fmt="pdf")
    assert pdf.startswith(b"%PDF")
    for bad in ({"fmt": "png", "path": "x.pdf"}, {"fmt": "exe"}, {"path": "no/such/dir/x.png"},
                {"dpi": 5}):  # fmt: skip
        with pytest.raises(Exception, match="must|cannot|format"):
            session.plots.export(fig["id"], **bad)


def test_documents_keep_figures(session, ventas):
    from framelab.session.document import from_document, to_document

    fig = figure_with(session, GALLERY["box"], name="fig_cajas")
    doc = to_document(session)
    restored, warnings = from_document(doc, {"ventas": ventas})
    try:
        assert warnings == []
        assert restored.plots.get(fig["id"])["spec"] == session.plots.get(fig["id"])["spec"]
        assert restored.plots.code(fig["id"]) == session.plots.code(fig["id"])
    finally:
        restored.close()


FIDELITY = ["line", "scatter", "grouped_bar", "hist", "box", "violin", "area", "heatmap"]


@pytest.mark.slow
@pytest.mark.parametrize("style", ["default", "ggplot"])
def test_copied_code_draws_the_same_image_as_the_export(session, ventas, tmp_path, style):
    """The script the user copies (pyplot, clean interpreter) == the export, pixel for pixel."""
    fig = session.plots.create("n1")
    spec = {**fig["spec"], "nrows": 2, "ncols": 4, "style": style, "width": 14, "height": 6}
    spec["axes"] = [{"layers": [GALLERY[k]], "title": k} for k in FIDELITY]
    session.plots.update(fig["id"], spec)
    expected = tmp_path / "expected.png"
    data, _ = session.plots.export(fig["id"], fmt="png", dpi=60)
    expected.write_bytes(data)
    ventas.to_pickle(tmp_path / "ventas.pkl")
    actual = tmp_path / "actual.png"
    script = session.plots.code(fig["id"]).replace(
        "plt.show()", f"fig_ventas.savefig({str(actual)!r}, dpi=60)"
    )
    program = (
        f"import pandas as pd\nventas = pd.read_pickle({str(tmp_path / 'ventas.pkl')!r})\n{script}"
    )
    env = {**os.environ, "MPLBACKEND": "Agg"}
    subprocess.run([sys.executable, "-c", program], check=True, env=env)
    assert compare_images(str(expected), str(actual), tol=2) is None
