import nbformat
import pytest
from nbclient import NotebookClient

pytestmark = pytest.mark.slow


def test_explore_displays_widget_in_kernel():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(
        nbformat.v4.new_code_cell(
            "import pandas as pd, framelab as fl\n"
            "ventas = pd.DataFrame({'a': range(1000), 'b': 0, 'c': 0, 'd': 0, 'e': 0})\n"
            "s = fl.explore(ventas)\n"
            "print(s.names)"
        )
    )
    NotebookClient(nb, timeout=120, kernel_name="python3").execute()
    outputs = nb.cells[0].outputs
    assert any("application/vnd.jupyter.widget-view+json" in o.get("data", {}) for o in outputs)
    assert any("['ventas']" in o.get("text", "") for o in outputs)
