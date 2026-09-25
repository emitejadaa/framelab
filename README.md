# framelab

## Instalación

1. Tené Python 3.11 o superior (Linux, Windows o macOS):

   ```bash
   python --version
   ```

2. Recomendado: creá un entorno virtual y activalo.

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   ```

3. Instalá framelab. `pip` instala también pandas, matplotlib y el resto de las dependencias; no hace
   falta Node ni compilar nada.

   ```bash
   pip install framelab
   ```

4. Comprobá que quedó instalado:

   ```bash
   python -c "import framelab; print(framelab.__version__)"
   ```

Para actualizar a la última versión: `pip install -U framelab`.

Extras opcionales:

```bash
pip install "framelab[desktop]"   # ventana nativa (pywebview) en lugar de una ventana del navegador
pip install "framelab[io]"        # leer y exportar Excel y otros formatos
```

Cada versión también está en [GitHub Releases](https://github.com/emitejadaa/framelab/releases/latest):
descargá el archivo `.whl` y corré `pip install framelab-<versión>-py3-none-any.whl`.

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
res["ventas_filt"]                    # el resultado de un nodo creado en la interfaz
res.code("ventas_filt")               # el código pandas que lo produce desde los datos originales
res.code("ventas_filt", mode="step")  # solo ese paso
res.names                             # los nombres de todos los nodos
res.figures["fig_ventas"]             # las figuras de matplotlib creadas en el Ploter
res.export("py", path="analisis.py")  # toda la sesión como script (o "ipynb" como notebook)
fl.last_session()                     # la sesión del último explore()
```

Las sesiones se guardan solas; para retomarlas, pasá de nuevo los datos:

```python
fl.open("last", ventas=ventas)   # la última sesión guardada
fl.autosaves()                   # las sesiones guardadas recientemente
```

Opciones:

```python
fl.options.general.language = "en"          # "auto", "es" o "en"
fl.set_option("general.theme", "dark")      # "system", "light" o "dark"
fl.set_option("general.open_mode", "window")
fl.set_option("code.style", "chained")      # código encadenado en vez de paso a paso
fl.set_option("code.filter_style", "query") # filtros con .query() cuando se puede
fl.get_option("general.language")
fl.reset_option("general.theme")
```

Desde la terminal, con archivos CSV, TSV, Parquet, JSON, Excel o Feather:

```bash
framelab ventas.csv clientes.parquet
```

---

## Installation

1. Python 3.11 or newer on Linux, Windows or macOS (`python --version`).
2. Recommended: create and activate a virtual environment
   (`python -m venv .venv`, then `source .venv/bin/activate` or `.venv\Scripts\activate` on Windows).
3. `pip install framelab` — pip also installs pandas, matplotlib and every other dependency; no Node
   and no compiling.
4. Check it: `python -c "import framelab; print(framelab.__version__)"`.

Upgrade with `pip install -U framelab`. Optional extras: `framelab[desktop]` (native window through
pywebview) and `framelab[io]` (Excel and other formats). Every version is also on
[GitHub Releases](https://github.com/emitejadaa/framelab/releases/latest): download the `.whl` and
`pip install` it.

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
res.export("ipynb", path="analysis.ipynb")   # the whole session as a notebook (or "py")

fl.open("last", sales=sales)       # reopen the last autosaved session with its data
fl.options.general.language = "en" # also general.theme, general.open_mode, code.style, …
```

```bash
framelab sales.csv customers.parquet
```

MIT © 2026 Emiliano Tejada
