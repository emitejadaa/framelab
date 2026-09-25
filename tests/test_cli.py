import pandas as pd
import pytest

from framelab.__main__ import load_table, variable_name


def test_load_by_extension(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    df.to_csv(tmp_path / "ventas 2024.csv", index=False)
    df.to_parquet(tmp_path / "v.parquet")
    df.to_json(tmp_path / "v.json", orient="records")
    pd.testing.assert_frame_equal(load_table(tmp_path / "ventas 2024.csv"), df)
    pd.testing.assert_frame_equal(load_table(tmp_path / "v.parquet"), df)
    assert list(load_table(tmp_path / "v.json").columns) == ["a", "b"]


def test_unknown_extension(tmp_path):
    (tmp_path / "x.foo").write_text("1")
    with pytest.raises(SystemExit):
        load_table(tmp_path / "x.foo")


def test_variable_name_from_file():
    assert variable_name("datos/ventas 2024-01.csv") == "ventas_2024_01"
    assert variable_name("2024.csv") == "df_2024"
