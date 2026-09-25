# framelab

## Instalación

```bash
pip install framelab
```

Requiere Python 3.11 o superior, en Linux, Windows o macOS. `pip` instala pandas, matplotlib y el resto de
las dependencias; no hace falta Node ni compilar nada.

Extras opcionales:

```bash
pip install "framelab[desktop]"   # ventana nativa (pywebview) en lugar de una ventana del navegador
pip install "framelab[io]"        # leer y exportar Excel y otros formatos
```

Para actualizar a la última versión: `pip install -U framelab`.

## Uso

```python
import pandas as pd
import framelab as fl

ventas = pd.read_csv("ventas.csv")
res = fl.explore(ventas)
```

- En un script, `explore()` abre una ventana, espera a que la cierres y devuelve la sesión.
- En Jupyter o en notebooks de VS Code, se muestra dentro del notebook y no bloquea la celda.

Varios DataFrames o Series, y nombres:

```python
fl.explore(ventas, clientes)       # los nombres salen de tus variables
fl.explore(ventas=df)              # nombre explícito
fl.explore(df, name="ventas")
fl.explore(ventas, mode="window")  # "auto" (por defecto), "inline" o "window"
```

La sesión devuelta:

```python
res["ventas_filt"]                 # el resultado de un nodo creado en la interfaz
res.code("ventas_filt")            # el código pandas que lo produce desde los datos originales
res.code("ventas_filt", mode="step")  # solo ese paso
res.names                          # los nombres de todos los nodos
res.figures["fig_ventas"]          # las figuras de matplotlib creadas en el Ploter
fl.last_session()                  # la sesión del último explore()
```

Opciones:

```python
fl.options.general.language = "en"          # "auto", "es" o "en"
fl.set_option("general.theme", "dark")      # "system", "light" o "dark"
fl.set_option("general.open_mode", "window")
fl.get_option("general.language")
fl.reset_option("general.theme")
```

Desde la terminal, con archivos CSV, TSV, Parquet, JSON, Excel o Feather:

```bash
framelab ventas.csv clientes.parquet
```

---

## Installation

```bash
pip install framelab
```

Python 3.11 or newer on Linux, Windows or macOS. `pip` installs pandas, matplotlib and every other
dependency; no Node and no compiling. Optional extras: `framelab[desktop]` (native window through
pywebview) and `framelab[io]` (Excel and other formats).

Upgrade with `pip install -U framelab`.

## Usage

```python
import pandas as pd
import framelab as fl

sales = pd.read_csv("sales.csv")
res = fl.explore(sales)            # a window from scripts (blocks until closed), inline in notebooks

fl.explore(sales, customers)       # several DataFrames or Series, named after your variables
fl.explore(sales=df)               # explicit names
fl.explore(sales, mode="window")   # "auto" (default), "inline" or "window"

res["sales_filt"]                  # a node's result
res.code("sales_filt")             # the pandas code that produces it (mode="step": that step only)
res.figures["fig_sales"]           # matplotlib figures built in the Plotter
fl.last_session()

fl.options.general.language = "en"   # also general.theme and general.open_mode; set_option/get_option
```

```bash
framelab sales.csv customers.parquet
```

MIT © 2026 Emiliano Tejada
