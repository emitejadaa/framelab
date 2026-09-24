# framelab — Especificación de diseño + plan de implementación

## Contexto
El usuario quiere una librería Python (idea original "plotExp", renombrada **framelab**) que, llamada desde
código con un DataFrame (`fl.explore(df)`), abra un entorno gráfico estilo mesa de trabajo (layout tipo
VS Code, interacción tipo Scratch/Bloodhound) para **explorar, transformar y graficar pandas DataFrames sin
escribir código**, usando **solo funciones/métodos existentes** de pandas y matplotlib, y mostrando siempre el
código Python exacto —con los nombres reales de variables y columnas— que reproduce cada resultado.
Carpeta local `/home/tejada/Desktop/plotExp` (vacía; se conserva el nombre local, el repo se llama `framelab`).
Entorno: Arch Linux (Wayland/Hyprland), Python 3.14.7, Node 25 (EOL) + pnpm, `gh` logueado como `emitejadaa`,
mise instalado, `/usr/bin/chromium`. `framelab` libre en PyPI. La especificación fue discutida y aprobada
sección por sección, investigada (4 agentes, versiones de sept-2026) y sometida a revisión crítica (3 agentes).

## Decisiones tomadas (confirmadas por el usuario)
| Tema | Decisión |
|---|---|
| Nombre | `framelab` · `pip install framelab` · `import framelab as fl` · `fl.explore(df)` |
| Stack | Backend Python + UI web TypeScript/React compilada dentro del wheel (usuario final sin Node) |
| Entornos | Scripts/CLI (ventana, bloquea como `plt.show()`, devuelve objetos) y Jupyter/VS Code (inline, no bloquea) |
| SO | Linux, Windows y macOS |
| Versiones mínimas | Python ≥ 3.11, pandas ≥ 3.0, matplotlib ≥ 3.11; pyarrow obligatoria |
| Datos objetivo | hasta ~1–5M filas |
| Idioma | UI español + inglés (i18n desde el día 1); tooltips de docs siempre en inglés original |
| Estética | minimalista, grises + 1 acento azul (~#3B82F6), claro/oscuro según sistema, poca animación |
| Nodos de datos | uno por operación; **inmutabilidad estricta** ("editar" crea hermano); sin recálculo en cascada |
| Vistas | Workbench, Tabla, Ploter; Tabla/Ploter se abren arrastrando un nodo a cajas del workbench |
| Código | paso a paso con variables por defecto (encadenado opcional); gráficos matplotlib OO |
| Fidelidad | se ejecuta una forma equivalente eficiente; tests prueban que todo código mostrado da resultado idéntico |
| Figuras | documentos editables con deshacer (no inmutables); separar por columna incluido |
| Funciones como argumento | nombres existentes + dicts + campo avanzado de expresión libre (lambda) |
| Errores | nodo de error rojo en el lienzo |
| Tabla | ver y operar; orden de encabezado visual + "convertir en paso"; modificar columna = copia + asignación |
| Preferencias | pantalla estilo VS Code + `fl.options` estilo `pd.options`; ayuda = tooltips de docs |
| Alcance | todo completo antes de publicar (internamente por hitos) |
| Sesiones | guardar/abrir `.framelab` + reaplicar receta a otros datos |
| Repo | GitHub público `emitejadaa/framelab`, MIT, commits directos a `main` |
| Ritmo | avanzar sin frenar entre hitos (resumen al final de cada uno) |
| Tests | Python fuerte (fidelidad); frontend mínimo (ver Política de tests) |
| Node dev | Node 24 LTS vía `mise.toml` |

## Especificación funcional

### API Python
- `fl.explore(ventas)`, `fl.explore(ventas, clientes)`, `fl.explore(ventas=df)`, `fl.explore(df, name="ventas")`,
  `fl.explore(..., mode="auto"|"inline"|"window", theme=, lang=)`; `fl.open("x.framelab", ventas=df)` y
  `fl.explore(recipe="x.framelab", ventas=nuevo_df)` (las raíces se vinculan por nombre).
- Script/CLI: bloquea hasta cerrar la ventana y devuelve `Session`: `res["ventas_head"]` (recalcula si fue
  liberado), `res.code()`, `res.figures` (dict nombre→`Figure`). `fl.last_session()` recupera la última.
- Jupyter: `explore()` hace `display()` del widget y devuelve un `Session` vivo con repr de texto corto.
  Re-ejecutar la celda **re-engancha** la sesión viva (`new=True` fuerza una nueva). `sess.add(clientes)` y en la
  app "Agregar variable del notebook" (lista DataFrames/Series del namespace). "Enviar al notebook" pregunta
  antes de sobrescribir una variable existente. "Abrir en ventana" (solo kernel local) colapsa el widget a
  "Abierto en ventana · Traer aquí" (un cliente activo a la vez).
- Matriz de detección de entorno: script, REPL, IPython terminal, JupyterLab/Notebook 7, VS Code notebook e
  Interactive, Colab, marimo, Spyder/qtconsole/PyCharm (sin widgets → modo ventana). Imports de
  anywidget/ipywidgets perezosos.
- CLI: `framelab ventas.csv` (CSV/Excel/Parquet/JSON); nombre de variable saneado desde el archivo.

### Workbench (vista 1)
- Layout: **barra de menú superior** (Archivo, Editar, Ver, Ayuda) · barra de pestañas (Workbench fija + una
  por tabla/figura) · explorador izq (nodos, figuras, pestañas, búsqueda) · lienzo React Flow · inspector der ·
  panel de código inferior colapsable · barra de estado (memoria, tareas con Cancelar, versiones) · cajas
  ▦ Tabla / ▟ Gráfico. Todo comando con atajo también tiene botón visible (paleta, preferencias).
- Tipos de nodo: DataFrame, Series, GroupBy (incl. selección de columnas `gb["monto"]`), Ventana
  (rolling/expanding/ewm/resample), Index, **Valor** (escalar, tupla, Timestamp, ndarray/list/dict con repr
  corto + shape/len, texto capturado de `info()`), **Figura** (nodo chico conectado a sus fuentes; dependiente,
  no descendiente) y **Error**.
- Estados de nodo: calculando · listo · error · bloqueado (ancestro en error) · cancelando → cancelado ·
  liberado (fuera de caché) · avisos (badge ámbar con warnings de pandas en el inspector).
- **Tabla de tipos de retorno** (regla del catálogo): DataFrame/Series/Index/GroupBy/Ventana/Resampler → su
  nodo; escalares/tuplas/Timestamp/Timedelta/Interval → nodo Valor (desde atributo: inline con "Crear nodo");
  ndarray/list/dict → Valor; None + salida impresa (`info`) → Valor de texto; métodos que mutan (`update`,
  `insert`) → plantilla copia+llamada (`v2 = v.copy(); v2.update(o)`); `pop` → nodo drop + Series; excluidos:
  `plot`/`hist`/`boxplot` (→ "Abrir en Ploter"), `style`, `iter*`, `flags`, `attrs`, `__dataframe__`. `to_*` de IO
  = acciones Exportar; conversores (`to_frame`, `to_period`, `to_numpy`, `to_dict`, `to_list`) = ops normales.
  Menús y "Todos A–Z" listan métodos **y atributos** (ícono propio).
- **Funciones de nivel superior** de pandas (subset de `reference/general_functions.rst`): `pd.to_datetime`,
  `pd.to_numeric`, `pd.to_timedelta`, `pd.cut`, `pd.qcut`, `pd.get_dummies`, `pd.concat`, `pd.crosstab`,
  `pd.merge`… aparecen en sus categorías y en el panel de columna, ligadas al primer argumento df/Series.
- Operar: clic derecho (buscador + categorías + "Todos A–Z"); inspector (resumen, mini-preview, atributos,
  métodos); paleta (Ctrl+Shift+P en ventana; F1/Ctrl+K en notebooks); arrastres (nodo sobre nodo → Combinar
  con `validate=`/`indicator=` y "ver claves duplicadas"; columna → Series; nodo a ▦/▟).
- Formularios auto-generados con código en vivo; constructor de filtro con operadores por dtype (== != < <= >
  >= between isin isna/notna str.contains/startswith rangos de fecha), literales parseados según el dtype de la
  columna y aviso de NaN en `!=`; constructor de selección (columnas, loc, iloc). Tras groupby, primer ítem
  "Elegir columnas a agregar"; aviso si la agregación tocaría columnas no numéricas (sugiere `numeric_only=True`).
- Validación previa (parámetros faltantes, columna inexistente, AST rechazado, guarda de tamaño) → error inline
  en el formulario, sin nodo. Excepción de pandas al ejecutar → **nodo de error** (mensaje explicado + traceback),
  "Editar como nuevo" para corregir; acción "Limpiar errores resueltos".
- **Reproducir rama**: al "Editar como nuevo" un nodo con descendientes (o un error con hijos bloqueados), opción
  explícita de recrear la cadena de descendientes bajo el hermano nuevo como nodos nuevos (no es cascada: el
  original queda intacto).
- Eliminar nodo: borra descendientes (confirmación con conteo y figuras dependientes: quitar capas afectadas /
  borrar figura / dejar capas marcadas rotas); se guarda como lápida para deshacer (reabre pestañas).
- Deshacer/rehacer por contexto (pestaña activa): Workbench/Tabla usan la pila del grafo; cada figura su historial.
- Auto-layout (dagre), minimapa, colapsar cadenas; en notebooks zoom del lienzo solo con Ctrl+rueda.
- Guardas de tamaño: estimación exacta O(n) de filas de merge/join (conteo de claves por lado) y de
  pivot/crosstab/get_dummies/explode; bloqueo sobre un % de RAM disponible (configurable) con override.
- **Copiar código en todo objeto**: cada menú de nodo tiene "Copiar código" (este paso / desde el origen /
  encadenado; Figura = pipeline de fuentes + figura; Error = código comentado + mensaje). Todo valor en pantalla
  producido por una llamada pandas tiene ícono de copiar esa llamada (`ventas.shape`, `ventas.isna().sum()`,
  `ventas["precio"].describe()`, `ventas.loc[42]`); resúmenes solo visuales (mini-histogramas) no.
- Nombres automáticos: tabla de alias por op (filtro → `_filt`, sort_values → `_sorted`, groupby+agg →
  `_by_<col>`, merge → `{izq}_{der}`, reset_index → `_reset`…), sufijos `_2`, `_3`, máximo ~30 caracteres
  (raíz + últimas ops), saneo (`isidentifier`, keywords, no pisar `pd`/`np`/builtins/variables del usuario),
  flag `name_auto` (los auto-nombres siguen a renombres del padre; los editados no). `DataFrame.filter` se
  rotula "filter (por etiquetas)".

### Tabla (vista 2)
- Encabezado con **← Workbench** (y Alt+←; vuelve con el nodo seleccionado y centrado), nombre, shape, memoria,
  buscar (Ctrl+F resalta), **Dividir** (dos tablas lado a lado).
- Columnas: nombre + badge dtype + mini histograma / top valores + % nulos (≈ si es estimado). Clic → panel de
  columna (describe, value_counts, únicos, nulos + ops de Series y funciones pd; destino: reemplazar / nueva /
  Series suelta). Multi-selección → seleccionar, borrar, agrupar, ordenar.
- Celdas: filtrar por valor, excluir, filtrar nulos, copiar, ver fila. Filas seleccionadas → nodo (`.loc[[labels]]`
  con índice único, rangos contiguos como slices; `.iloc[[pos]]` si no; siempre orden real, no el visual).
- Orden por encabezado = visual + "convertir en paso". Cambiar datos crea nodo (aviso con "abrir" y
  "abrir aquí"); ver/formatear/buscar no.
- Variantes: Series (+ value_counts), GroupBy (grupos → `get_group`), Index.

### Ploter (vista 3, una pestaña por figura)
- Entrada: ▟ siempre crea figura nueva (1 eje, el nodo como fuente, galería abierta con 2–3 sugerencias por
  dtype, sin gráfico automático); soltar un nodo en la pestaña de una figura la abre con los ejes resaltados
  como destino; encabezado con **← Workbench**.
- Izq: árbol Figura → Ejes (grilla / mosaico / twinx) → Capas (reordenables) con **chip de fuente** por capa
  (soltar otro nodo = revincular, validando columnas/dtypes); lista de nodos del workbench arrastrables.
- Galería por familias con contrato de datos por familia: líneas/áreas, barras (bar/barh/grouped_bar),
  distribución (hist/boxplot con `dropna()`/violinplot/ecdf), dispersión/hexbin, pie, grilla 2D
  (imshow/pcolormesh/contour/hist2d toman df ancho; sugerencia "crear pivot en el workbench"), tri* (formato
  largo x/y/z), errorbar/stem, polar. Fuentes de mapeo: columnas, **índice**, niveles de MultiIndex, valores e
  índice de una Series. `label=` automático si hay leyenda.
- **Filas** (por capa, u opcional a nivel de fuente de la figura): todas, head(n), tail(n), rango iloc,
  sample(n, random_state), condiciones Y/O (mismo constructor del workbench), "filas seleccionadas en Tabla".
  Genera una línea de preparación con nombre dentro del código de la figura
  (`ventas_plot = ventas.loc[ventas["region"] == "Norte"]`) + botón "Crear nodo en el workbench".
- **Separar por columna** → bucle `for k, g in df.groupby(col)`.
- Modelo de ejes con **llamadas ordenadas** (allowlist tipada): tick_params (rotación), grid, legend,
  set_xticks/labels, locators/formatters (mdates/mticker), spines, margins, invert_*axis, set_axisbelow; y
  **artistas** (text/annotate/axhline/axvline/axhspan). Orden de emisión fijo: capas → artistas → llamadas de
  ejes → títulos/etiquetas → leyenda → límites. "Ticks" y "Leyenda" dentro de "Comunes".
- Centro: preview en vivo (debounce ~200 ms; al esperar, el último frame queda atenuado con spinner, nunca en
  blanco); herramientas seleccionar/zoom/pan/reset; clic selecciona; arrastrar título/leyenda/anotaciones;
  decimación recalculada para los límites visibles en cada zoom; límites de fechas sin tz si el eje es naive.
- Der: propiedades de Figura / Ejes / Capa ("Comunes" + "Todas A–Z").
- Código de figura: modos **"completo"** (default de Copiar: imports usados, pipelines de todas las fuentes sin
  duplicar en orden topológico, filas, figura, `fig.savefig(ruta)` si se exportó, `plt.show()` según
  preferencia —sí en scripts, no en notebooks—) y "solo figura". Variables por figura `fig_<nombre>`,
  `ax_<nombre>` / `axs_<nombre>` / `axd_<nombre>` (nombre editable; usado en código, exports, `res.figures`,
  "Enviar al notebook"). Estilo emitido como `with plt.style.context("…"):`. Línea base de rcParams = snapshot
  de `matplotlib.rcParams` del usuario al llamar `explore()` (preferencia: rcParamsDefault).
- Errores de capa: capa roja en el árbol con mensaje, se conserva el último preview bueno, exportar deshabilitado.
- Exportar PNG/SVG/PDF/JPG (dpi, tamaño, transparente, bbox) **escrito por Python** en la ruta elegida (relativa
  al cwd del proceso; esa misma ruta va al código); en notebooks también descarga. Vector con >N puntos → aviso
  y opción `rasterized=True` visible en el código.
- "Duplicar con…" (reemplazar cada fuente por otro nodo; opción mantener límites de zoom, off por defecto).
  **Plantilla** = spec de figura con ranuras de fuente abstractas + columnas requeridas; aplicarla = "Duplicar con…".

### Estados de carga y movimiento
- Arranque: loader HTML/CSS inline antes de parsear el bundle → "Conectando…" hasta handshake + snapshot;
  el widget reserva altura fija con el mismo loader.
- Operaciones: spinner en la tarjeta + entrada en barra de estado con Cancelar, solo tras ~150–200 ms; tiempo
  transcurrido tras ~2 s; "terminando operación no interrumpible…" al cancelar algo en curso.
- Tabla: filas esqueleto para bloques no recibidos; placeholders en stats de encabezado.
- Pestañas: el marco aparece al instante y el contenido se completa.
- Movimiento: ~150 ms ease-out (opacidad + 4–8 px) para vistas, pestañas, paneles y menús; sin animar el
  lienzo salvo re-layout opcional; respeta `prefers-reduced-motion` + preferencia "Reducir animaciones".
- Notebooks: si el kernel está ocupado (>1 s sin respuesta) → "Kernel ocupado — framelab responderá al
  terminar la celda" (+ sugerencia "Abrir en ventana" si el kernel es local).

### Preferencias
- Pantalla estilo VS Code: buscador + categorías, descripción y "restablecer" por opción; accesible por
  engranaje y Ctrl+, (en ventana).
- General (idioma, tema, acento, tamaño/densidad, modo de apertura, altura inline ~720 px, reducir animaciones,
  confirmaciones) · Workbench (patrón/alias de nombres, auto-layout, minimapa, filas de mini-preview, snap) ·
  Tabla (decimales, miles, fechas, histogramas, ancho) · Código (paso a paso/encadenado, máscara/query,
  copia+asignación/assign, alias de imports, incluir imports, comillas, `plt.show()` en código completo,
  inline de intermedios perezosos —off por defecto—) · Gráficos (estilo, tamaño, dpi, formato, en vivo/manual +
  debounce, umbral de muestreo, paleta/colormap, base de rcParams) · Rendimiento (memoria de caché, tope de
  memoria fijada, umbral de estadísticas aproximadas, % RAM para guardas) · Atajos (editables, por entorno) ·
  Avanzado (expresiones libres, carpeta de sesiones, autosave, logs).
- Cambios de estilo de código a mitad de sesión regeneran todo el código mostrado (aviso "código
  regenerado"); cambios del patrón de nombres aplican solo a nodos nuevos; nombres de variables nunca se
  traducen; mensajes de error se guardan como código + parámetros y se muestran en el idioma actual.
- Ayuda: tooltips al hover con la descripción breve de las docstrings oficiales (inglés) + link a la doc.

### Sesiones y recetas
- `.framelab` = JSON versionado (`format_version` + versiones por sección + registro de migraciones): ops del
  grafo, posiciones, pestañas, figuras, prefs de sesión; nunca código crudo. Registro de fuente por raíz:
  archivo (ruta relativa + absoluta, lector y kwargs exactos de `read_*`, hash de esquema) o memoria (nombre de
  variable, shape, dtypes, hash de esquema).
- Abrir sesión: `fl.open(path, ventas=df)` / Archivo → Abrir; raíces no resolubles → diálogo "Vincular fuentes"
  (selector de archivo de Python o variable del kernel) con diff de esquema; si no coincide → "abrir como receta".
- Aplicar receta: diálogo previo que vincula raíces y **mapea columnas faltantes** (sugerencias por nombre,
  acentos, similitud y dtype; avisa deriva de dtypes); lo que siga sin resolver → nodo de error con descendientes
  bloqueados + "Reproducir rama" tras corregir. Auto-nombres se regeneran desde la nueva raíz; editados se conservan.
- **Autosave** con debounce tras cada cambio en `platformdirs.user_data_dir("framelab")/sessions/`; confirmación
  al cerrar (Ctrl+W, Ctrl+R, beforeunload) si no se guardó; "Recuperar última sesión" al volver a abrir.
- Archivos siempre leídos/escritos por Python mediante un **explorador de archivos propio** (rutas reales en
  el código; en kernels remotos navega el filesystem del kernel); diálogos nativos de pywebview opcionales.
- Exports `.py` con raíces en memoria incluyen comentario `# Requiere: ventas (DataFrame 1000×5: fecha, …)`.

## Arquitectura técnica

### Estado y protocolo
- **Python es la fuente de verdad** de grafo, posiciones, pestañas/layout, modelos de figura, pilas de deshacer
  y prefs de sesión. El frontend usa stores Zustand **por widget** (fábrica en contexto React, sin singletons de
  módulo) hidratados con `session.snapshot(rev)` y actualizados por eventos numerados.
- Envelope: `{v, id, type: req|res|evt|cancel, method, params, error:{code, i18n_key, message, traceback},
  buffers:[idx]}`; handshake `{protocol_version, framelab_version}` con pantalla de incompatibilidad; eventos
  `node.upserted`, `node.state`, `task.progress`, `cache.evicted`, `figure.changed`, `tabs.changed`; payloads
  navegador→kernel troceados bajo 10 MiB. **Tipos TS generados desde esquemas Python** (TypedDict/JSON Schema)
  y el contrato se testea en pytest.
- Transporte: `Dispatcher` Python agnóstico + adaptadores WebSocket (Starlette + uvicorn + `websockets`, hilo
  daemon) y anywidget comms; frontend con interfaz `Transport` (WS / anywidget).

### Procesos, hilos y ventanas
- Motor en el proceso del usuario con **dos carriles**: cómputo (1 hilo serializado para ops nuevas) y lectura
  (1–2 hilos que sirven ventanas Arrow, stats, value_counts y resúmenes solo desde resultados cacheados
  inmutables). Renderer matplotlib en su propio hilo. **Resultado S3:** p95 de ventanas ≤ 24 ms bajo carga,
  pero agregaciones sobre columnas de texto retienen el GIL toda la llamada (13–37 s de bloqueo) → se mantiene
  el hilo en proceso (un subproceso duplicaría cada raíz, >1 GB para 5M×30); la UI trata todo pedido de datos
  como asíncrono (esqueletos/spinners); el aviso "la agregación toca columnas no numéricas" pasa a ser una
  **guarda** previa; se re-mide en M8 y, si hiciera falta, el cómputo pasa a un subproceso dueño de los datos.
- Cancelación suave (contador de generación); ops encoladas detrás sí se cancelan de verdad.
- **Política de preview por op** (en el catálogo): `rowwise` (muestra segura: filtros, astype, .str/.dt,
  aritmética, head/tail reales), `sampled_stat` (≈ con tamaño de muestra), `global` (sin preview por muestra:
  sort, value_counts, merge, rank, cumsum, rolling, pivot…). Las previews por muestra solo aparecen en el panel
  en vivo del formulario; tarjetas y Tabla muestran solo resultados completos.
- Hijos creados sobre un padre aún calculando esperan su resultado completo.
- Servidor local: 127.0.0.1, puerto aleatorio, token de 32 bytes entregado por archivo redirect 0600 (patrón
  Jupyter), token requerido en `/`, assets y WS, chequeo de `Origin` y `Host`, sin CORS — **criterio de
  aceptación de M0 (cumplido)**. `/?token=` sirve la página directamente (sin 303: tras una navegación iniciada
  desde `file://` el salto sería cross-site y perdería la cookie `SameSite=Strict`) y limpia la URL con
  `history.replaceState`; el archivo redirect se borra apenas el navegador se conecta.
- Ventana: pywebview (extra `framelab[desktop]`; preferido en Windows/macOS) → Chrome/Chromium/Edge/Brave
  `--app=URL --no-first-run --no-default-browser-check --user-data-dir=<tmp por lanzamiento>` (preferido en
  Linux; `Popen.wait`; limpieza del tmp) → `webbrowser.open` + cierre tras autosave y gracia configurable (~60 s)
  sin cliente WS. En Linux+NVIDIA con WebKitGTK: `WEBKIT_DISABLE_DMABUF_RENDERER=1`.
- Jupyter: anywidget 0.11; raíz con `data-lm-suppress-shortcuts` y `data-jp-suppress-context-menu`; teclado solo
  con foco dentro de `.fl-root`; ResizeObserver; altura ~720 px + redimensionar + maximizar; portapapeles con
  fallback (execCommand → modal con el código seleccionado); "Abrir en ventana" vía
  `subprocess.Popen([sys.executable, "-m", "framelab._window", url])`.

### Motor pandas, catálogo y codegen
- Raíz congelada con `df.copy(deep=False)` (CoW).
- **Esquema de op (primera tarea de M1)**: `Op{schema_v, kind: call|attr|getitem|setitem|filter|select|combine|
  func, target: node_id, accessor: [...], name, args: [Value], kwargs: {str: Value}}`;
  `Value = {t: lit|col|node|func|expr|ts|nan|tuple|list|pairs, …}` (dicts como pares para claves no string);
  groupby/rolling/resample producen su propio nodo; se estampan versiones de esquema y de pandas.
- Catálogo: allowlist + categorías desde `doc/source/reference/*.rst` (incluido `general_functions.rst`) de la
  versión de referencia → JSON en el repo; introspección runtime (`inspect.getattr_static`); miembros no
  presentes en el JSON (pandas más nuevo) aparecen bajo "Otros" por introspección; `.str/.dt/.cat` sobre
  `node[col].head(0)`. Cada entrada con `returns`, `mutates`, `preview_policy`, categoría y esquema de
  parámetros: defaults de `inspect.signature`, tipos de anotaciones resueltas contra `pandas._typing`
  (Literal → enum), fallback a línea de tipo de numpydoc (**numpydoc solo en build**; en runtime el fallback es
  signature + primera línea de docstring), overrides manuales (~60 métodos + `GroupBy.__getitem__`). Lo privado
  envuelto en adaptadores con tests. **Resultado S6:** 89,8 % de 2313 parámetros → control concreto (98,3 % de
  los nombrados); tipos de control extra `scalar` y `values`; guardar candidatos/nullable/choices por parámetro;
  la marca `.. deprecated::` se busca solo antes de la primera sección numpydoc (si no, se descartan merge,
  astype…); ocultar parámetros deprecados (`copy`); nunca pasar `inplace` (pandas 3 devuelve self o None
  según el método e `interpolate(inplace=True)` muta y luego falla); editores especiales para `assign(**kw)`,
  agregación con nombre, args de `apply`, `eval/query`, `GroupBy.filter/nth/__getitem__`; funciones `pd.*` en
  tabla curada (solo 6 de 12 anotan su primer argumento). Prototipo: `docs/superpowers/spikes/artifacts/`.
- Codegen: **emisor propio** para el subconjunto de nodos generados (Call, Attribute, Subscript, Name, Constant,
  contenedores, Compare, BoolOp, UnaryOp, Lambda), comillas dobles, salida validada con `ast.parse`; literales
  especiales (NaN→`np.nan`, numpy→`.item()`, Timestamp→`pd.Timestamp('ISO')`, tuplas MultiIndex); siempre
  `df["col"]` y kwargs. Renderizados: paso a paso / encadenado (variables en ramas, entradas múltiples, fuentes
  de figura y nombres exportados) / máscara o query (fallback a máscara con comentario) / copia+asignación o
  assign / alias de imports.
- Ejecución: se ejecuta la **forma canónica eficiente** de cada op (`compile` + linecache + `exec` en un solo
  dict con `pd`, `np`, padres y raíz con su nombre real), validada contra allowlist de AST. **Decisión del
  usuario (P1): forma equivalente verificada** — lo mostrado puede diferir en forma de lo ejecutado (p. ej.
  `v.copy()` mostrado vs `v.copy(deep=False)` ejecutado; máscara vs query; assign interno para columnas en
  tablas grandes), y la suite de fidelidad prueba que **toda variante mostrada da resultado idéntico** a la
  ejecutada. En modo debug/tests se verifica que los padres no cambian tras ejecutar.
- Nombre de variable: `name=`/kwargs → `varname.argname(vars_only=False)` → escaneo por identidad de
  `f_locals`/`f_globals` (ignorando `_`, `_N`, `In`, `Out`) → `df`; expresión (`dfs[0]`) → `root = dfs[0]`.
- Caché LRU por bytes (~25% RAM, psutil): cuenta buffers únicos (CoW), fija raíces, nodos con pestaña abierta y
  fuentes transitivas de figuras abiertas, con tope de memoria fijada (sobre el tope se liberan pestañas ocultas
  menos vistas → "liberado"); recompute desde el ancestro cacheado. Al cerrar la ventana el `Session` conserva
  raíces y recalcula perezosamente.

### Motor de gráficos
- Solo `Figure` + `FigureCanvasAgg` (nunca pyplot en el backend), hilo de render con lock y cola "latest-wins",
  `matplotlib.style.context` envolviendo build+draw+export; fuente de rcParams según preferencia.
- Modelo: Figure{figsize, dpi, layout, facecolor, style, suptitle, var_name} → Grid{subplots|mosaic} →
  Axes{twin_of, props, calls[], artists[]} → Layers[{method, source_node, rows_filter, mapping, split_by, kwargs}].
  Cabecera exportada `fig_x, ax_x = plt.subplots(...)` vs ejecutada `Figure(...)` + `fig.subplots(...)`, cuerpo
  idéntico; solo se emite lo que el usuario fijó.
- Preview a dpi = base × devicePixelRatio (tope dpr 2), PNG propio (filtro 0 + zlib nivel 1 directo desde
  `buffer_rgba()`, ~2,5× más rápido que Pillow); reducción solo en preview (**S5**): líneas/step/fill_between →
  M4 por columna de píxel (salida idéntica); scatter → muestra aleatoria determinística de **20 000** puntos;
  scatter con `c=` → muestra + cuantización de color (en crudo tarda 28–38 s con 1M); hist/hexbin/boxplot/barras
  agregadas → datos completos; estilo "fast" solo en preview; `rcParams.copy()` (nunca `dict(rcParams)`, que
  importa pyplot).
- Hit-map JSON por frame (bboxes con y invertida, bbox/lims/escalas por eje, polilíneas decimadas; ids por diff
  de `ax.get_children()`); interacción local; traducción al soltar con recetas de DraggableLegend /
  DraggableAnnotation / `set_title(x=,y=)` / `transData.inverted()` + `num2date` (sin tz en ejes naive).
- Propiedades tipadas desde stubs `.pyi` (ast) + `matplotlib.typing` + registros; `ArtistInspector` solo
  docs/fallback; allowlist curada; esquema generado en build (JSON) con fallback runtime.

### Frontend
- React 19.3, Vite 8.3 (lib mode, ESM único, `codeSplitting: false`, assets/fuentes inline, un CSS), TS 7
  (`tsc --noEmit`) + oxlint, Zustand 5 por widget, `<Activity>` para pestañas ocultas.
- Lienzo @xyflow/react 12.11 + @dagrejs/dagre 3.1. **Nodos del lienzo usan el drag propio de React Flow**
  (`onNodeDrag`/`onNodeDragStop` + `getIntersectingNodes` para combinar; hit-test por DOMRect de cajas y barra
  de pestañas; el nodo vuelve a su posición tras soltar). **Módulo DnD por pointer events** solo para fuentes
  externas: sidebar→lienzo, columna del inspector→Series, lista de nodos del Ploter→ejes. @dnd-kit solo para
  listas ordenables. **S10:** apagar `autoPanOnNodeDrag` mientras el puntero está fuera del lienzo y restaurar
  el viewport tras soltar afuera (si no, deriva 23–180 px); fantasma del nodo en el portal fuera del lienzo.
- Grilla Glide Data Grid 6.0.4-alpha24 (pin exacto) tras un adaptador (fallback AG Grid Community); bloques
  Arrow decodificados con @uwdata/flechette; columnas problemáticas (tipos mixtos, nombres duplicados, listas)
  con fallback a string + badge; ids posicionales + labels como metadata. **S1:** parche de una línea al
  `InfiniteScroller` (sin él, a DPR fraccional no se llega a las últimas ~774 filas) vía pnpm
  `patchedDependencies`; `portalElementRef` al portal de `.fl-root`; tema de Glide con colores ya resueltos (su
  parser usa un div en `document.body`). **S7:** encoder Arrow v2 (plan por columna cacheado por nodo, nunca
  `astype(str)` sobre object, formateador acotado), decodificación con `{useBigInt, useDecimalInt}`.
- UI: shadcn/ui sobre Base UI 1.8 + Tailwind 4.3 con prefijo, reset y tokens scopeados a `.fl-root`; **un
  PortalContainer dentro de `.fl-root`** para menús, popovers, tooltips, paleta (cmdk) y fantasmas de DnD;
  react-resizable-panels 4.13; i18next + react-i18next; Shiki 4 fine-grained; react-colorful; lucide-react;
  fuentes Inter + JetBrains Mono (OFL, subset latin, licencias en el wheel). Presupuesto < ~800 KB gz; bundle
  minificado a nivel Rolldown (viaja completo en el `comm_open` de cada widget).
- **Aislamiento CSS (S2):** dentro de JupyterLab el CSS sin capas del host le gana al reset y a las utilidades
  en `@layer` → **spike S12 al inicio de M2a**: Shadow DOM (verificar Glide, React Flow, Base UI, cmdk y
  `@property` de Tailwind dentro de un shadow root) vs. utilidades `important` + reset sin capa. `.fl-root` es
  enfocable y toma el foco al hacer clic (si no, los atajos del notebook se disparan); los menús propios hacen
  `preventDefault()` del menú nativo; el tema debe seguir al de JupyterLab/VS Code, no solo al del sistema.

### Empaquetado y toolchain
- `pyproject.toml` con hatchling + hook de build (hatch-jupyter-builder ≥0.10 con `npm="pnpm"` o `hatch_build.py`
  propio, usando `mise exec -- pnpm` si mise está disponible) → `src/framelab/_static/` como `artifacts`,
  `skip-if-exists`; wheel puro `py3-none-any`; sdist instalable sin Node.
- Deps runtime: `pandas>=3.0,<4`, `matplotlib>=3.11,<4` (adaptadores degradan con gracia + CI contra la última y
  nightly), numpy, pyarrow, anywidget>=0.11, starlette, uvicorn, websockets, varname[all], psutil, platformdirs.
  Extras: `desktop` (pywebview>=6.2), `io` (openpyxl, tabulate, jinja2, lxml… — acciones sin dependencia quedan
  grises con "pip install …"). `.ipynb` escrito como JSON nbformat v4 a mano (nbformat solo en dev para validar).
- Dev (`[dependency-groups] dev`): pytest, hypothesis, ruff, pytest-benchmark, numpydoc, nbformat, nbclient,
  ipykernel, jupyterlab. Frontend: Vitest 5 (scaffolding), Playwright 1.63, @jupyterlab/galata.
- `mise.toml`: `node = "24"`, `pnpm` exacto; `packageManager` en `frontend/package.json`; `mise trust && mise install`.
- `.gitignore`: `.venv/`, `node_modules/`, `src/framelab/_static/`, `frontend/dist/`, `__pycache__/`,
  `.pytest_cache/`, `playwright-report/`, `test-results/`, `*.egg-info/`, `dist/`, `build/`.
- Dev loop: `pnpm dev` (Vite :5173, proxy WS a Python :8765) + `FRAMELAB_DEV=1`.

## Política de tests (preferencia del usuario)
- **Frontend mínimo**: sin TDD en frontend; tests Vitest de andamio en `frontend/tests/scaffold/`
  (`*.scaffold.test.ts`), excluidos de CI y **borrados al cerrar cada hito** (ítem de checklist). Contratos
  (protocolo, ops, catálogo, prefs) se generan desde Python y se prueban en pytest.
- **Presupuesto E2E total (6)**, solo en Linux: abrir ventana desde script · head(5) + copiar código · arrastrar a
  ▦/▟ · scroll de tabla + filtrar por celda crea nodo · arrastrar leyenda cambia el código · 1 smoke Galata en
  JupyterLab. Windows/macOS en CI: tests Python + prueba headless del lanzador. Herramienta: `playwright-core`
  manejando el Chromium del sistema (el MCP de chrome-devtools requiere Google Chrome); en CI Chrome corre con
  `--no-sandbox` (los runners Ubuntu 24.04 bloquean los user namespaces del sandbox).
- **Python fuerte** (TDD): fidelidad (script exportado ejecutado en intérprete limpio == resultado del nodo,
  hypothesis sobre etiquetas difíciles, todas las combinaciones de estilos de código, funciones pd, remapeo de
  recetas, reproducir rama), goldens del codegen, catálogo, motor, protocolo (snapshot → rehidratación), ploter.
- Figuras: comparar el script exportado (intérprete limpio, Agg, fuentes fijadas) contra el **camino de export**
  en proceso con `matplotlib.testing.compare.compare_images(tol≈2)`, nunca contra el preview; el preview se
  verifica estructuralmente (hit-map, límites, cantidad de artistas).
- Cada plan detallado de hito copia esta sección tal cual.

## Estructura del repo
```
framelab/                      (carpeta local: /home/tejada/Desktop/plotExp)
├─ pyproject.toml · mise.toml · LICENSE (MIT, © 2026 emitejadaa) · README.md (es/en) · hatch_build.py
├─ src/framelab/
│  ├─ __init__.py  api.py  options.py  cli.py  _window.py  env.py (detección de entorno)
│  ├─ protocol/  (esquemas, envelope, eventos → genera tipos TS)
│  ├─ session/   (dag, nodos, estados, comandos/deshacer, serialize .framelab, recetas, autosave, fuentes)
│  ├─ engine/    (carril cómputo, carril lectura, caché, guardas, nombres)
│  ├─ catalog/   (JSON generado, introspección, parámetros, overrides, docs, retorno/mutación/preview)
│  ├─ codegen/   (op schema, emisor, literales, estilos, export py/ipynb, ejecución)
│  ├─ table/     (ventanas arrow, stats de columnas)
│  ├─ plot/      (modelo, renderer, hitmap, drag→código, esquema mpl, codegen)
│  ├─ files/     (explorador de archivos del lado Python)
│  ├─ transport/ (dispatcher, servidor ws seguro, widget)
│  ├─ launch/    (pywebview, chromium app, navegador)
│  └─ _static/   (bundle compilado, gitignored)
├─ frontend/src/ (shell, workbench, table, plotter, prefs, transport, dnd, i18n, ui, theme, generated/)
├─ tools/        (generadores: catálogo pandas, esquema matplotlib, tipos TS)
├─ spikes/       (spikes descartables de M0, borrados al cerrar M0)
├─ tests/        · frontend/tests/{scaffold,e2e}
├─ docs/superpowers/specs/2026-09-23-framelab-design.md   (fuente de verdad; se actualiza con cada decisión)
└─ .github/workflows/
```

## Hitos internos (rebanadas verticales; sin release hasta M8)
Cada hito arranca con un plan detallado (skill writing-plans, copiando la Política de tests), TDD en Python,
cierra con verificación + borrado de tests de andamio + resumen breve al usuario, commits directos a `main`.

- **M0 — Base + spikes + contratos.** Repo/venv/mise/licencia/README/.gitignore/spec (ver Primeros pasos);
  pyproject + hook; esqueleto frontend (lib build → `_static`); protocolo (esquemas, envelope, handshake, tipos
  TS generados); Transport WS + anywidget; servidor seguro (checklist de seguridad = aceptación); cadena de
  ventanas; detección de entorno + `mode=`; registro de opciones (clave/tipo/default/categoría/i18n) leído por
  codegen; i18next + tokens de tema + `.fl-root` + PortalContainer; CI esqueleto. **Spikes descartables**
  (decisión por cada uno): S1 Glide+React19 en ventana/JupyterLab/Notebook7/VS Code con 5M filas · S2 bundle
  anywidget realista (tiempo de render, aislamiento CSS, dos widgets en una página, menús contextuales,
  atajos) · S3 transporte bajo carga GIL (p95 lectura < 250 ms o subproceso) · S4 matriz de lanzadores (cierre
  detectado < 1 s, sin first-run, dos `explore()` concurrentes) · S5 presupuesto de render matplotlib
  (≤150 ms preview, PNG ≤400 KB, `plt.figure(fig)` con Figure()) · S6 censo de introspección de pandas
  (% de parámetros con widget) · S7 robustez Arrow (dtypes raros) · S8 varname + detección de entorno en
  3.11–3.14 · S9 sdist sin Node · S10 DnD React Flow (drag interno + cajas externas + combinar) · S11
  `v.copy()` vs `copy(deep=False)` en memoria/tiempo con pandas 3. *Verificar:* `fl.explore(df)` muestra
  "ventas · 1000 × 5" en script (bloquea/devuelve) y en JupyterLab; wheel con `_static`.
- **M1a — Núcleo mínimo.** Esquema de op + dataclasses, DAG + estados, codegen paso a paso + ejecución, motor
  (dos carriles) básico, ~20 ops curadas, endpoints de resumen de nodo y ventana Arrow, envoltorio `.framelab`
  (versionado, sin congelar). *Verificar:* pytest de fidelidad sobre las 20 ops.
- **M2a — Workbench mínimo de punta a punta.** Shell (menú, pestañas, paneles, explorador, inspector con
  mini-preview vía Arrow, código, estado), lienzo con nodos, flujo head(5) completo, copiar código, pestañas
  Tabla/Ploter provisorias para que ▦/▟ funcionen, loader de arranque. *Verificar:* E2E 1–3.
- **M1b — Núcleo completo.** Estilos de codegen restantes, caché/desalojo, generador de catálogo completo
  (retorno/mutación/preview_policy, funciones pd, overrides), nombres automáticos, deshacer por contexto,
  guardas, nodos de error/bloqueado/cancelado, reproducir rama, export .py/.ipynb, autosave.
- **M2b — Workbench completo.** Menús por categorías + A–Z + atributos, formularios auto-generados con código
  en vivo, paleta, filtro y selección, combinar por arrastre + diálogo merge/join/concat con estimación,
  editar como nuevo, eliminar con lápidas, colapsar, minimapa, íconos de copiar en valores, tooltips, estados
  de carga y movimiento, i18n es/en de todo lo construido.
- **M3 — Tabla.** Adaptador Glide, bloques Arrow + esqueletos, histogramas, panel de columna (+ funciones pd),
  menús de celda/fila/columna, orden visual + convertir, buscar, dividir, variantes, "abrir aquí".
  *Verificar:* E2E 4; scroll fluido de 5M filas mientras corre una op larga (benchmark/manual).
- **M4 — Catálogo completo en UI.** Formularios para todo (DataFrame/Series/GroupBy/Ventanas/Resampler/Index +
  accessors + funciones pd), funciones como argumento + expresión libre + confianza, exportaciones `to_*`
  (extra io), reporte de cobertura. *Verificar:* cobertura + fidelidad sobre todos los métodos.
- **M5 — Ploter núcleo.** Modelo (calls/artists/rows/split), renderer, codegen completo/solo figura, galería
  (formularios a mano para plot/bar/hist/scatter/boxplot; el resto desde el esquema), mapeo (índice incluido),
  filas, separar por columna, paneles de propiedades, preview en vivo + decimación, exportar escrito por
  Python, nodos figura, multi-df, revincular fuente, duplicar con…, deshacer. *Verificar:* diff de imagen
  export vs script exportado.
- **M6 — Ploter interacción y estilo.** Hit-map, selección, arrastres → código, zoom/pan → límites, anotaciones,
  líneas de referencia, estilos, ciclos, colormaps, fuentes, plantillas. *Verificar:* E2E 5.
- **M7 — Preferencias, sesiones, Jupyter, archivos.** Pantalla de preferencias + `fl.options` + persistencia +
  atajos por entorno, UI de sesiones/recetas (vincular fuentes, mapeo de columnas), explorador de archivos
  Python, CLI, "Enviar al notebook", "Agregar variable", re-enganche de celda, "Abrir en ventana", kernel ocupado,
  traducciones completas. *Verificar:* E2E 6 (Galata), tests de CLI y recetas.
- **M8 — Endurecimiento y publicación.** Benchmarks 1M/5M, ajuste de guardas y caché, accesibilidad básica,
  CI verde (3 SO × Python 3.11–3.14 + pandas/matplotlib últimas), docs es/en, re-auditoría de seguridad,
  tamaño de wheel/bundle, release 0.1.0 a PyPI (requiere cuenta/token del usuario → única pausa prevista).

## Riesgos principales y mitigación
- APIs privadas/provisionales de pandas y matplotlib → adaptadores, tests por versión, CI contra últimas/nightly,
  fallback por introspección.
- Glide Data Grid en alpha → validado en S1, pin exacto, adaptador, fallback AG Grid Community.
- Sin cancelación dura y contención del GIL → carriles separados, guardas exactas, política de preview; S3 decide
  si el cómputo va a subproceso.
- Kernel de Jupyter ocupado / sin widgets → aviso de kernel ocupado, matriz de entornos, modo ventana.
- Estado global de matplotlib → nunca pyplot en backend, lock, style context acotado, snapshot de rcParams.
- Ventanas nativas en Linux → Chromium `--app` por defecto.
- Ejecución de código (expresiones libres, sesiones ajenas, servidor local) → op JSON, allowlist de AST,
  confianza explícita, token + Origin/Host desde M0.
- Pérdida de trabajo → Python dueño del estado, autosave, confirmaciones, re-enganche.

## Forma de trabajo
- Avanzar sin frenar entre hitos; resumen breve al cerrar cada uno (qué se hizo, cómo probarlo, qué sigue).
  Solo me detengo ante bloqueos reales (credenciales, p. ej. PyPI en M8) o decisiones irreversibles no cubiertas.
- Commits chicos y descriptivos directo a `main` con push a `emitejadaa/framelab`.
- La spec en `docs/superpowers/specs/` es la fuente de verdad y se actualiza cuando cambia una decisión.
- Memoria del proyecto: guardar como feedback la política de tests mínimos en frontend y el ritmo "sin frenar".

## Primeros pasos al salir de plan mode
1. En `/home/tejada/Desktop/plotExp`: `git init -b main`; `mise.toml` (node 24 + pnpm exacto) + `mise trust &&
   mise install`; `python3 -m venv .venv`; `LICENSE` (MIT), `README.md`, `.gitignore`.
2. Copiar esta especificación a `docs/superpowers/specs/2026-09-23-framelab-design.md`; commit inicial.
3. `gh repo create emitejadaa/framelab --public --source . --push`.
4. Guardar memorias del proyecto (feedback de tests y ritmo).
5. Invocar writing-plans para el plan detallado de M0 (spikes + contratos) y ejecutarlo; seguir con M1a…M8.

