import json
import os
import pickle
import subprocess
import sys

import nbformat
import pytest

from framelab.errors import BadRequest
from framelab.naming import RootSpec
from framelab.ops.build import call, col, getitem, gt, mul, node, ref_col, setcol, where
from framelab.options import build_default_registry
from framelab.session import NodeError, Session
from test_fidelity import assert_same, make_frames


def build(options=None):
    registry = build_default_registry()
    for key, value in (options or {}).items():
        registry.set(key, value)
    ventas, clientes = make_frames()
    s = Session([RootSpec("ventas", ventas), RootSpec("clientes", clientes)], registry)
    a = s.apply(where("n1", gt(col("monto"), 50)))
    b = s.apply(setcol(a.id, "total", mul(col("monto"), col("cantidad"))))
    c = s.apply(call(b.id, "groupby", by=ref_col("pais")))
    d = s.apply(getitem(c.id, "total"))
    e = s.apply(call(d.id, "sum"), name="por_pais")
    merged = s.apply(call("n1", "merge", node("n2"), on="id", how="left"))
    bad = s.apply(getitem("n1", "no_existe"))
    fig = s.plots.create(e.id)
    spec = fig["spec"]
    spec["axes"][0]["layers"] = [{"kind": "bar", "source": e.id}]
    s.plots.update(fig["id"], spec)
    s.wait(e.id)
    s.wait(merged.id)
    with pytest.raises(NodeError):
        s.wait(bad.id)
    return s


def run_script(script, tmp_path):
    ventas, clientes = make_frames()
    ventas.to_pickle(tmp_path / "v.pkl")
    clientes.to_pickle(tmp_path / "c.pkl")
    out = tmp_path / "out.pkl"
    program = (
        "import pandas as pd\n"
        f"ventas = pd.read_pickle({str(tmp_path / 'v.pkl')!r})\n"
        f"clientes = pd.read_pickle({str(tmp_path / 'c.pkl')!r})\n"
        f"{script}\n"
        "import pickle\n"
        "found = {k: v for k, v in dict(globals()).items()"
        " if not k.startswith('_') and isinstance(v, (pd.DataFrame, pd.Series))}\n"
        f"pickle.dump(found, open({str(out)!r}, 'wb'))\n"
    )
    subprocess.run(
        [sys.executable, "-c", program], check=True, env={**os.environ, "MPLBACKEND": "Agg"}
    )
    with open(out, "rb") as fh:
        return pickle.load(fh)


@pytest.mark.parametrize(
    "options",
    [{}, {"code.style": "chained"}, {"code.filter_style": "query", "code.quote": "single"}],
)
def test_exported_script_reproduces_every_node(tmp_path, options):
    s = build(options)
    try:
        values = run_script(s.export("py")["text"], tmp_path)
        tables = ("DataFrame", "Series")  # what the script run pickles back
        ready = [
            n
            for n in s.nodes()
            if n.state.value == "ready" and not n.is_root and n.kind.value in tables
        ]
        if not options:
            assert {n.name for n in ready} <= set(values)
        assert "por_pais" in values
        for n in ready:
            if n.name in values:
                assert_same(s.wait(n.id), values[n.name])
    finally:
        s.close()


def test_script_layout():
    s = build()
    try:
        text = s.export("py")["text"]
        assert text.startswith(
            "# framelab session: ventas, clientes\n"
            "# Requires: ventas (DataFrame 6 × 7: id, fecha, pais, monto, cantidad, …)\n"
            "# Requires: clientes (DataFrame 4 × 2: id, nombre)\n\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n"
        )
        assert "# ventas_no_existe = ventas[\"no_existe\"]\n# ↑ KeyError: 'no_existe'" in text
        assert "fig_por_pais, ax_por_pais = plt.subplots(" in text
        assert text.endswith("plt.show()\n")
    finally:
        s.close()


def test_notebook_is_valid():
    s = build()
    try:
        notebook = json.loads(s.export("ipynb")["text"])
        nbformat.validate(nbformat.from_dict(notebook))
        kinds = [c["cell_type"] for c in notebook["cells"]]
        assert kinds[:3] == ["markdown", "markdown", "code"]
        assert any("por_pais = " in c["source"] for c in notebook["cells"])
        assert not any("plt.show()" in c["source"] for c in notebook["cells"])
    finally:
        s.close()


def test_export_writes_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = build()
    try:
        out = s.export("py", path="sesion.py")
        assert out["path"] == str(tmp_path / "sesion.py")
        assert (tmp_path / "sesion.py").read_text(encoding="utf-8") == out["text"]
        for bad in ("sesion.txt", "no/dir/x.py"):
            with pytest.raises(BadRequest):
                s.export("py", path=bad)
        with pytest.raises(BadRequest):
            s.export("csv")
    finally:
        s.close()
