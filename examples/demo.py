"""framelab demo: python examples/demo.py (from the repo root, with .venv active)."""

import threading
import time

import numpy as np
import pandas as pd

import framelab as fl
from framelab.ops.build import call, col, getitem, gt, mul, ref_col, setcol, where

rng = np.random.default_rng(7)
ventas = pd.DataFrame(
    {
        "fecha": pd.date_range("2024-01-01", periods=12, freq="MS"),
        "pais": rng.choice(["AR", "UY", "BR", "CL"], 12),
        "monto": rng.integers(50, 500, 12).astype(float),
        "cantidad": rng.integers(1, 6, 12),
    }
)

# Until the visual workbench (M2a) exists, operations are applied from Python.
# The window opens and updates live as each node is computed.


def build(sesion):
    filtro = sesion.apply(where("n1", gt(col("monto"), 150)))
    con_total = sesion.apply(setcol(filtro.id, "total", mul(col("monto"), col("cantidad"))))
    grupos = sesion.apply(call(con_total.id, "groupby", by=ref_col("pais")))
    totales = sesion.apply(getitem(grupos.id, "total"))
    suma = sesion.apply(call(totales.id, "sum"))
    sesion.apply(call(suma.id, "sort_values", ascending=False), name="ranking")


def when_ready():
    while fl.last_session() is None:
        time.sleep(0.05)
    time.sleep(1.5)  # let the window connect so you see the nodes appear
    build(fl.last_session())


threading.Thread(target=when_ready, daemon=True).start()
sesion = fl.explore(ventas)  # blocks until you close the window

print("\nRanking:\n", sesion["ranking"])
print("\nCódigo:\n" + sesion.code("ranking"))
