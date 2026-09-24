# framelab

> 🇪🇸 Explorá, transformá y graficá DataFrames de pandas **sin escribir código** — y copiá siempre el código Python exacto que lo hace.
> 🇬🇧 Explore, transform and plot pandas DataFrames **without writing code** — and always copy the exact Python code that does it.

```python
import framelab as fl

fl.explore(ventas)   # abre la mesa de trabajo / opens the workbench
```

**Estado / Status:** en desarrollo temprano (pre-alpha). Todavía no está publicado en PyPI.
Early development (pre-alpha). Not yet published on PyPI.

## Qué es / What it is

Una mesa de trabajo visual (estilo VS Code, interacción tipo Scratch) donde cada operación de pandas crea
un nuevo nodo inmutable conectado a su origen. Cada nodo muestra el código Python real —con tus nombres de
variables y columnas— que lo produce. Arrastrá cualquier nodo a la vista de **Tabla** para explorarlo, o a la
vista de **Gráfico** para construir figuras de matplotlib con todas sus propiedades.

A visual workbench (VS Code-like layout, Scratch-like interaction) where every pandas operation creates a new
immutable node linked to its source. Every node shows the real Python code —with your own variable and column
names— that produces it. Drag any node to the **Table** view to explore it, or to the **Plot** view to build
matplotlib figures with all their properties.

- Solo métodos y funciones existentes de pandas y matplotlib — nada inventado.
- Funciona desde scripts (ventana propia) y dentro de Jupyter / VS Code notebooks.
- Interfaz en español e inglés.

## Diseño / Design

La especificación completa está en
[`docs/superpowers/specs/2026-09-23-framelab-design.md`](docs/superpowers/specs/2026-09-23-framelab-design.md).

## Desarrollo / Development

Requisitos: Python ≥ 3.11, [mise](https://mise.jdx.dev) (Node 24 + pnpm fijados en `mise.toml`).

```bash
mise trust && mise install
python3 -m venv .venv && source .venv/bin/activate
```

## Licencia / License

MIT © 2026 Emiliano Tejada
