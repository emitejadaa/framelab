import pandas as pd
import pytest

from framelab.catalog import load, owner_types

OWNERS = {
    "DataFrame", "Series", "DataFrameGroupBy", "SeriesGroupBy", "Resampler", "Rolling",
    "Expanding", "ExponentialMovingWindow", "Index", "str", "dt", "cat", "pd",
}  # fmt: skip


@pytest.fixture(scope="module")
def catalog():
    return load()


def test_every_owner_is_there(catalog):
    assert set(catalog.owners) == OWNERS
    assert catalog.pandas_version.startswith("3.")


def test_head(catalog):
    head = catalog.member("DataFrame", "head")
    assert head.category == "Indexing, iteration"
    assert head.summary.startswith("Return the first")
    [n] = head.params
    assert (n.name, n.widget, n.required, n.default) == ("n", "int", False, 5)
    assert (head.returns, head.mutates, head.preview, head.allowed) == (
        "DataFrame",
        False,
        "rowwise",
        True,
    )


def test_parameters(catalog):
    params = {p.name: p for p in catalog.member("DataFrame", "sort_values").params}
    assert params["by"].widget == "columns" and params["by"].required
    assert params["ascending"].widget == "bool" and params["ascending"].default is True
    keep = {p.name: p for p in catalog.member("DataFrame", "drop_duplicates").params}["keep"]
    assert keep.widget == "choice" and "first" in keep.choices


def test_return_kinds_and_mutation(catalog):
    assert catalog.member("DataFrame", "groupby").returns == "GroupBy"
    assert catalog.member("Series", "rolling").returns == "Window"
    assert catalog.member("DataFrame", "shape").returns == "Value"
    assert catalog.member("str", "upper").returns == "Series"
    assert catalog.member("dt", "year").returns == "Series"
    for name in ("insert", "pop", "update"):
        assert catalog.member("DataFrame", name).mutates, name
    assert not catalog.member("DataFrame", "sort_values").mutates


def test_policy_and_categories(catalog):
    assert not catalog.member("DataFrame", "to_csv").allowed
    assert not catalog.member("DataFrame", "plot").allowed
    assert catalog.member("str", "upper").category == "String handling"
    assert catalog.member("pd", "concat").category == "Data manipulations"
    assert catalog.member("DataFrame", "describe").preview == "sampled_stat"


def test_generated_members_exist_at_runtime(catalog):
    for owner, cls in owner_types().items():
        names = [m.name for m in catalog.members(owner) if m.generated]
        missing = [n for n in names if not hasattr(cls, n)]
        assert len(missing) <= 0.03 * len(names), (owner, missing)


def test_members_missing_from_the_file_appear_under_other(catalog, monkeypatch):
    known = dict(catalog._members["DataFrame"])
    known.pop("head")
    monkeypatch.setitem(catalog._members, "DataFrame", known)
    head = catalog.member("DataFrame", "head")
    assert head.category == "Other" and not head.generated
    assert "head" in [m.name for m in catalog.members("DataFrame")]


def test_the_file_is_small():
    from importlib import resources

    size = len(resources.files("framelab.catalog").joinpath("pandas.json.gz").read_bytes())
    assert size < 400_000


def test_catalog_method():
    from framelab.naming import RootSpec
    from framelab.session import Session
    from framelab.transport.dispatcher import Dispatcher

    s = Session([RootSpec("v", pd.DataFrame({"a": [1]}))])
    try:
        env, _ = Dispatcher(s).handle(
            {
                "v": 1,
                "id": "1",
                "type": "req",
                "method": "catalog.members",
                "params": {"owner": "Series"},
            },
            [],
        )
        names = [m["name"] for m in env["result"]["members"]]
        assert "value_counts" in names and env["result"]["pandas_version"].startswith("3.")
    finally:
        s.close()
