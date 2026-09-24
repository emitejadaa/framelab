import threading
import warnings

import pandas as pd
import pytest

from framelab.engine import ComputeLane, UnsafeCode, run_statement


@pytest.fixture
def ventas():
    return pd.DataFrame({"monto": [1.0, 2.0, 3.0], "pais": ["AR", "UY", "AR"]})


def test_runs_generated_statement(ventas):
    value, warns = run_statement("out = ventas.head(n=2)", "out", {"ventas": ventas})
    pd.testing.assert_frame_equal(value, ventas.head(2))
    assert warns == []


def test_two_line_setitem(ventas):
    code = 'v2 = ventas.copy(deep=False)\nv2["x"] = v2["monto"] * 2'
    value, _ = run_statement(code, "v2", {"ventas": ventas})
    assert list(value["x"]) == [2.0, 4.0, 6.0]
    assert "x" not in ventas.columns


def test_literals_can_use_pd_np_datetime_decimal(ventas):
    code = (
        'out = ventas.assign(t=pd.Timestamp("2024-01-01"), n=np.nan, d=datetime.date(2024, 1, 1))'
    )
    value, _ = run_statement(code, "out", {"ventas": ventas})
    assert value["t"].iloc[0] == pd.Timestamp("2024-01-01")


def test_warnings_are_captured_not_raised(ventas):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a leaked warning would raise here
        _, warns = run_statement('out = np.log(ventas["monto"] - 10)', "out", {"ventas": ventas})
    assert any(w.startswith("RuntimeWarning") for w in warns)


def test_tracebacks_point_at_generated_code(ventas):
    with pytest.raises(KeyError) as info:
        run_statement('out = ventas["nope"]', "out", {"ventas": ventas})
    assert "<framelab:out>" in "".join(__import__("traceback").format_tb(info.tb))


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "out = __import__('os')",
        "out = ventas.__class__",
        "out = ventas._mgr",
        "out = open('/etc/passwd')",
        "out = (lambda: 1)()",
        "out = [x for x in ventas]",
        "other = ventas",
        "out = ventas; ventas.x = 1",
        "del ventas",
        "out = eval('1')",
        "out = ventas.head(n=1)\nventas['z'] = 1",
    ],
)
def test_rejects_unsafe_code(code, ventas):
    with pytest.raises(UnsafeCode):
        run_statement(code, "out", {"ventas": ventas})


def test_compute_lane_runs_jobs_in_order_on_one_thread():
    lane = ComputeLane()
    seen = []
    futures = [
        lane.submit(lambda i=i: seen.append((i, threading.current_thread().name))) for i in range(5)
    ]
    for f in futures:
        f.result(timeout=5)
    assert [i for i, _ in seen] == [0, 1, 2, 3, 4]
    assert len({name for _, name in seen}) == 1
    lane.shutdown()
