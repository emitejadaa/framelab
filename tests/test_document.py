import json

import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, col, gt, ref_col, where
from framelab.session import Session
from framelab.session.document import (
    FORMAT_VERSION,
    MIGRATIONS,
    DocumentError,
    from_document,
    load,
    save,
    to_document,
)


@pytest.fixture
def ventas():
    return pd.DataFrame({"pais": ["AR", "UY", "AR"], "monto": [10.0, 20.0, 30.0]})


def build(ventas):
    s = Session([RootSpec("ventas", ventas)])
    f = s.apply(where("n1", gt(col("monto"), 15)))
    s.apply(call(f.id, "sort_values", by=ref_col("monto")), name="ordenado")
    s.wait("ordenado")
    return s


def test_roundtrip_rebuilds_ids_names_and_results(ventas, tmp_path):
    s = build(ventas)
    path = tmp_path / "trabajo.framelab"
    save(s, path)
    doc = load(path)
    assert doc["format"] == "framelab" and doc["format_version"] == FORMAT_VERSION
    s2, warnings = from_document(doc, {"ventas": ventas})
    assert warnings == []
    assert [(n.id, n.name, n.name_auto) for n in s2.nodes()] == [
        (n.id, n.name, n.name_auto) for n in s.nodes()
    ]
    pd.testing.assert_frame_equal(s2.wait("ordenado"), s.wait("ordenado"))
    s.close()
    s2.close()


def test_document_stores_ops_not_code(ventas):
    s = build(ventas)
    text = json.dumps(to_document(s))
    assert "sort_values" in text and "import" not in text and "exec" not in text
    s.close()


def test_missing_root_is_reported(ventas):
    s = build(ventas)
    with pytest.raises(DocumentError, match="ventas"):
        from_document(to_document(s), {})
    s.close()


def test_schema_change_is_a_warning(ventas):
    s = build(ventas)
    changed = ventas.assign(extra=1)
    s2, warnings = from_document(to_document(s), {"ventas": changed})
    assert warnings and "ventas" in warnings[0]
    s.close()
    s2.close()


def test_future_versions_are_rejected(ventas, tmp_path):
    s = build(ventas)
    doc = to_document(s)
    doc["format_version"] = FORMAT_VERSION + 1
    path = tmp_path / "x.framelab"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DocumentError, match="newer"):
        load(path)
    s.close()


def test_migrations_registry_starts_empty():
    assert MIGRATIONS == {}


def test_not_a_framelab_file(tmp_path):
    path = tmp_path / "x.framelab"
    path.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(DocumentError):
        load(path)
