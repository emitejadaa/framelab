"""The Combine dialog's numbers: exact rows per join type, duplicate keys and dtype problems."""

import pandas as pd
import pytest

from framelab.engine.combine import describe_merge
from framelab.errors import BadRequest
from framelab.naming import RootSpec
from framelab.ops.values import encode_scalar
from framelab.session import Session

VENTAS = pd.DataFrame(
    {
        "cliente": [1, 2, 2, 3, 4],
        "monto": [10.0, 20, 30, 40, 50],
        "fecha": pd.date_range("2024", periods=5),
    }
)
CLIENTES = pd.DataFrame({"cliente": [1, 2, 3, 3, 9], "pais": ["AR", "UY", "CL", "PE", "BR"]})


def rows(left, right, **kw):
    out = {
        how: len(left.merge(right, how=how, **kw)) for how in ("inner", "left", "right", "outer")
    }
    return {**out, "cross": len(left) * len(right)}


def test_rows_match_pandas_for_every_join_type():
    out = describe_merge(VENTAS, CLIENTES, {"on": ["cliente"]})
    assert out["rows"] == rows(VENTAS, CLIENTES, on="cliente")
    assert out["rows"]["cross"] == len(VENTAS) * len(CLIENTES)
    assert out["columns"]["inner"] == len(VENTAS.merge(CLIENTES, on="cliente").columns)


def test_duplicate_keys_and_the_relation():
    out = describe_merge(VENTAS, CLIENTES, {"on": ["cliente"]})
    assert out["duplicates"] == {"left": 2, "right": 2}  # rows whose key repeats on that side
    assert out["relation"] == "many_to_many"
    unique = describe_merge(VENTAS, CLIENTES.drop_duplicates("cliente"), {"on": ["cliente"]})
    assert unique["relation"] == "many_to_one" and unique["duplicates"]["right"] == 0


def test_keys_from_the_index_and_different_names():
    by_index = CLIENTES.set_index("cliente")
    out = describe_merge(VENTAS, by_index, {"left_on": ["cliente"], "right_index": True})
    assert out["rows"] == rows(VENTAS, by_index, left_on="cliente", right_index=True)
    renamed = CLIENTES.rename(columns={"cliente": "id"})
    out = describe_merge(VENTAS, renamed, {"left_on": ["cliente"], "right_on": ["id"]})
    assert out["rows"] == rows(VENTAS, renamed, left_on="cliente", right_on="id")


def test_keys_pandas_cannot_merge_are_reported():
    text = CLIENTES.assign(cliente=CLIENTES["cliente"].astype(str))
    out = describe_merge(VENTAS, text, {"on": ["cliente"]})
    assert out["mismatch"] == [
        {"left": "cliente", "right": "cliente", "left_dtype": "int64", "right_dtype": "str"}
    ]
    dates = describe_merge(VENTAS, CLIENTES, {"left_on": ["fecha"], "right_on": ["cliente"]})
    assert dates["mismatch"] and dates["mismatch"][0]["left_dtype"].startswith("datetime64")


def test_no_usable_keys():
    out = describe_merge(VENTAS, pd.DataFrame({"x": [1]}), {})
    assert out["rows"] == {"cross": len(VENTAS)}
    assert out["relation"] is None and out["duplicates"] is None


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS), RootSpec("clientes", CLIENTES)])
    yield session
    session.close()


def test_session_combine_info(s):
    key = [encode_scalar("cliente")]
    out = s.combine_info("n1", "n2", left_on=key, right_on=key)
    assert out["common"] == [encode_scalar("cliente")]
    assert out["rows"]["left"] == len(VENTAS.merge(CLIENTES, on="cliente", how="left"))
    assert out["relation"] == "many_to_many"
    assert s.combine_info("n1", "n2")["rows"]["inner"] == out["rows"]["inner"]  # common columns


def test_session_combine_info_checks_its_inputs(s):
    with pytest.raises(BadRequest):
        s.combine_info(
            "n1", "n2", left_on=[encode_scalar("nope")], right_on=[encode_scalar("cliente")]
        )
    with pytest.raises(BadRequest):
        s.combine_info("n1", "n2", left_on=[encode_scalar("cliente")], right_on=[])


def test_combine_info_over_the_protocol(s):
    from framelab.transport.dispatcher import Dispatcher

    params = {
        "left": "n1",
        "right": "n2",
        "left_on": [encode_scalar("cliente")],
        "right_on": [encode_scalar("cliente")],
    }
    env, _ = Dispatcher(s).handle(
        {"v": 1, "id": "c1", "type": "req", "method": "node.combine_info", "params": params}, []
    )
    assert env["result"]["relation"] == "many_to_many"
    env, _ = Dispatcher(s).handle(
        {
            "v": 1,
            "id": "c2",
            "type": "req",
            "method": "node.combine_info",
            "params": {"left": "n1", "right": "n2", "left_on": "x"},
        },
        [],
    )
    assert env["error"]["code"] == "bad_request"
