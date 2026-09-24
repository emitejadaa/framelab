"""S3b: worst-case UI blocking (max window latency) per typical pandas operation on 5M rows."""

import threading
import time

import numpy as np
import pandas as pd
import pyarrow as pa
from websockets.sync.client import connect

from framelab.naming import RootSpec
from framelab.protocol import PROTOCOL_VERSION, decode_frame, encode_frame
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher, Reply
from framelab.transport.server import FramelabServer

N = 5_000_000
rng = np.random.default_rng(0)
df = pd.DataFrame({f"c{i}": rng.random(N) for i in range(10)})
df["k"] = rng.integers(0, 1000, N)
df["s"] = pd.Series(rng.integers(0, 10**5, N)).astype(str)          # pandas 3 'str' (pyarrow)
df["o"] = df["s"].astype(object)                                      # legacy object dtype
other = pd.DataFrame({"k": np.arange(1000), "w": rng.random(1000)})
table = pa.Table.from_pandas(df[["c0", "c1", "k"]], preserve_index=False)

OPS = {
    "groupby numeric sum": lambda: df.groupby("k")[[f"c{i}" for i in range(10)]].sum(),
    "groupby sum (all cols)": lambda: df.drop(columns=["o"]).groupby("k").sum(),
    "sort_values": lambda: df.sort_values("c0"),
    "merge m:1": lambda: df.merge(other, on="k"),
    "str.upper (pyarrow str)": lambda: df["s"].str.upper(),
    "str.upper (object)": lambda: df["o"].str.upper(),
    "apply lambda (100k)": lambda: df["c0"].head(100_000).apply(lambda x: x * 2),
    "describe": lambda: df.describe(),
    "value_counts str": lambda: df["s"].value_counts(),
}

d = Dispatcher(Session([RootSpec("big", df.head(3))]))


def window(params, bufs):
    o = int(params["offset"])
    sink = pa.BufferOutputStream()
    part = table.slice(o, 200)
    with pa.ipc.new_stream(sink, part.schema) as w:
        w.write_table(part)
    return Reply({}, [sink.getvalue().to_pybytes()])


d.register("spike.window", window)
srv = FramelabServer(d, "/tmp")
srv.start()
url = f"ws://127.0.0.1:{srv.port}/ws?token={srv.token}"
with connect(url, origin=f"http://127.0.0.1:{srv.port}") as ws:
    for name, op in OPS.items():
        done = threading.Event()
        dur = {}

        def run(op=op, done=done, dur=dur):
            t0 = time.perf_counter()
            op()
            dur["t"] = time.perf_counter() - t0
            done.set()

        threading.Thread(target=run, daemon=True).start()
        lat = []
        i = 0
        while not done.is_set():
            env = {"v": PROTOCOL_VERSION, "id": str(i), "type": "req",
                   "method": "spike.window", "params": {"offset": (i * 7919) % (N - 200)}}
            t0 = time.perf_counter()
            ws.send(encode_frame(env))
            decode_frame(ws.recv(timeout=120))
            lat.append((time.perf_counter() - t0) * 1000)
            i += 1
        lat.sort()
        p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else float("nan")
        print(f"{name:<26} op={dur['t']:6.2f}s  requests={len(lat):5d}  "
              f"p95={p95:8.1f} ms  max={lat[-1] if lat else float('nan'):9.1f} ms", flush=True)
srv.stop()
