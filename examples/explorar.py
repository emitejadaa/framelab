"""Open the workbench on a realistic sample dataset: python examples/explorar.py"""

import numpy as np
import pandas as pd

import framelab as fl

rng = np.random.default_rng(42)
n = 500
ventas = pd.DataFrame(
    {
        "fecha": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 365, n), unit="D"),
        "pais": rng.choice(
            ["Argentina", "Uruguay", "Chile", "Brasil", "Perú"], n, p=[0.4, 0.15, 0.2, 0.15, 0.1]
        ),
        "canal": rng.choice(["online", "tienda", "mayorista"], n),
        "producto": rng.choice(["notebook", "monitor", "teclado", "mouse", "auriculares"], n),
        "cantidad": rng.integers(1, 20, n),
        "precio unitario": rng.choice([1200.0, 350.0, 45.5, 20.0, 80.0], n),
        "descuento": rng.choice([0.0, 0.05, 0.1, np.nan], n, p=[0.6, 0.2, 0.1, 0.1]),
    }
)
ventas.loc[rng.choice(n, 12, replace=False), "canal"] = None

fl.explore(ventas)
