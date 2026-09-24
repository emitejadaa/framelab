import functools
import sys

import pandas as pd
import pytest

from framelab.naming import (
    RootSpec,
    resolve_root_names,
    sanitize_identifier,
    scan_frame_for,
    unique_name,
    user_frame,
)


def fake_explore(*args, name=None, **kwargs):
    frame = user_frame(sys._getframe(1))
    return resolve_root_names(args, kwargs, frame, explicit_name=name, callee=fake_explore)


@pytest.fixture
def ventas():
    return pd.DataFrame({"a": [1, 2]})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ventas", "ventas"),
        ("ventas 2024-01", "ventas_2024_01"),
        ("2024", "df_2024"),
        ("class", "df_class"),
        ("pd", "df_pd"),
        ("list", "df_list"),
        ("año", "año"),
        ("", "df"),
        ("---", "df"),
    ],
)
def test_sanitize_identifier(text, expected):
    assert sanitize_identifier(text) == expected


def test_unique_name():
    assert unique_name("x", set()) == "x"
    assert unique_name("x", {"x"}) == "x_2"
    assert unique_name("x", {"x", "x_2"}) == "x_3"


def test_single_variable(ventas):
    specs = fake_explore(ventas)
    assert specs == [RootSpec("ventas", ventas, None)]
    assert specs[0].obj is ventas


def test_two_variables(ventas):
    clientes = pd.DataFrame({"b": [1]})
    specs = fake_explore(ventas, clientes)
    assert [s.name for s in specs] == ["ventas", "clientes"]


def test_multiline_call(ventas):
    specs = fake_explore(
        ventas,
    )
    assert specs[0].name == "ventas"


def test_subscript_expression(ventas):
    dfs = [ventas]
    specs = fake_explore(dfs[0])
    assert specs[0].name == "dfs_0"
    assert specs[0].source_expr == "dfs[0]"


def test_call_expression_falls_back_to_df():
    specs = fake_explore(pd.DataFrame({"a": [1]}))
    assert specs[0].name == "df"
    assert specs[0].source_expr is None


def test_keyword_names(ventas):
    df = ventas
    specs = fake_explore(sales=df)
    assert specs == [RootSpec("sales", ventas, "df")]
    assert specs[0].obj is ventas


def test_explicit_name(ventas):
    specs = fake_explore(ventas, name="mis ventas")
    assert specs[0].name == "mis_ventas"


def test_explicit_name_needs_single_positional(ventas):
    with pytest.raises(ValueError, match="name="):
        fake_explore(ventas, ventas, name="x")


def test_same_object_twice_is_deduplicated(ventas):
    specs = fake_explore(ventas, ventas)
    assert [(s.name, s.source_expr) for s in specs] == [("ventas", None), ("ventas_2", "ventas")]


def test_no_source_uses_identity_scan(ventas):
    ns = {"fake_explore": fake_explore, "ventas_sin_fuente": ventas}
    exec("result = fake_explore(ventas_sin_fuente)", ns)
    assert ns["result"][0].name == "ventas_sin_fuente"


def test_identity_scan_skips_ipython_noise(ventas):
    scopes = {"f_locals": {"_": ventas, "_3": ventas, "Out": {}}, "f_globals": {"x": ventas}}
    frame = type("F", (), scopes)()
    assert scan_frame_for(ventas, frame) == ["x"]


def test_nothing_found_defaults_to_df():
    ns = {"fake_explore": fake_explore, "pd": pd}
    exec("result = fake_explore(pd.DataFrame({'a': [1]}))", ns)
    assert ns["result"][0].name == "df"


captured = []


def capturing_explore(*args, **kwargs):
    frame = user_frame(sys._getframe(1))
    captured.append(resolve_root_names(args, kwargs, frame, callee=capturing_explore))
    return 0


def test_used_as_sort_key_is_not_named_after_the_outer_call(ventas):
    # sorted() is C code, so executing reports sorted(one, ...) itself; its first
    # argument is the list, not the DataFrame -> must fall back to the identity scan.
    captured.clear()
    one = [ventas]
    sorted(one, key=capturing_explore)
    assert captured[-1][0].name == "ventas"


def test_partial_falls_back_to_identity_scan(ventas):
    specs = functools.partial(fake_explore)(ventas)
    assert specs[0].name == "ventas"


def test_pipe_skips_pandas_internal_frames(ventas):
    specs = ventas.pipe(fake_explore)
    assert specs[0].name == "ventas"
