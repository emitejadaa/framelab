"""Memory accounting for node results: bytes per node, least-recently-used eviction, pins.

Buffers that belong to the roots are not counted: views of the user's data cost nothing extra
(Copy-on-Write). Everything else is counted per node, which over-counts views shared between
nodes and so errs on the side of freeing memory early.
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from typing import Any

import numpy as np
import pandas as pd
import psutil

__all__ = ["ResultCache", "buffers", "default_budget", "value_bytes"]


def _base(arr: np.ndarray) -> np.ndarray:
    while isinstance(arr.base, np.ndarray):
        arr = arr.base
    return arr


def _array_buffers(arr: Any) -> list[tuple[int, int]]:
    if isinstance(arr, np.ndarray):
        base = _base(arr)
        return [(base.__array_interface__["data"][0], int(base.nbytes))]
    if isinstance(arr, pd.arrays.ArrowExtensionArray):
        import pyarrow as pa

        data = arr.__arrow_array__()
        chunks = data.chunks if isinstance(data, pa.ChunkedArray) else [data]
        return [(b.address, b.size) for c in chunks for b in c.buffers() if b is not None]
    for attr in ("asi8", "codes"):  # datetime/timedelta/period arrays, categoricals
        inner = getattr(arr, attr, None)
        if isinstance(inner, np.ndarray):
            return _array_buffers(inner)
    return [(id(arr), int(getattr(arr, "nbytes", 0) or 0))]


def _column_buffers(s: pd.Series) -> list[tuple[int, int]]:
    if isinstance(s.dtype, np.dtype):
        return _array_buffers(s.to_numpy(copy=False))
    return _array_buffers(s.array)


def _index_buffers(index: pd.Index) -> list[tuple[int, int]]:
    if isinstance(index, pd.RangeIndex):
        return []
    if isinstance(index, pd.MultiIndex):
        return [(id(index), int(index.memory_usage()))]
    if isinstance(index.dtype, np.dtype):
        return _array_buffers(index.to_numpy(copy=False))
    return _array_buffers(index.array)


def buffers(value: Any) -> list[tuple[int, int]]:
    """(address, size) of the memory behind a value; views share their base's address."""
    try:
        if isinstance(value, pd.DataFrame):
            out: list[tuple[int, int]] = []
            for j in range(value.shape[1]):
                out += _column_buffers(value.iloc[:, j])
            return out + _index_buffers(value.index)
        if isinstance(value, pd.Series):
            return _column_buffers(value) + _index_buffers(value.index)
        if isinstance(value, pd.Index):
            return _index_buffers(value)
        if isinstance(value, np.ndarray):
            return _array_buffers(value)
    except Exception:  # an exotic dtype: fall back to pandas' own estimate
        usage = getattr(value, "memory_usage", None)
        total = usage(deep=False) if callable(usage) else 0
        return [(id(value), int(getattr(total, "sum", lambda: total)()))]
    return [(id(value), sys.getsizeof(value))]  # scalars; groupby objects reference their parent


def value_bytes(value: Any, exclude: set[int] | frozenset[int] = frozenset()) -> int:
    seen: set[int] = set()
    total = 0
    for address, size in buffers(value):
        if address in exclude or address in seen:
            continue
        seen.add(address)
        total += size
    return total


def default_budget(fraction: float) -> int:
    return int(psutil.virtual_memory().total * fraction)


class ResultCache:
    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.pinned: set[str] = set()
        self._sizes: OrderedDict[str, int] = OrderedDict()

    @property
    def total(self) -> int:
        return sum(self._sizes.values())

    def add(self, nid: str, nbytes: int) -> None:
        self._sizes[nid] = nbytes
        self._sizes.move_to_end(nid)

    def touch(self, nid: str) -> None:
        if nid in self._sizes:
            self._sizes.move_to_end(nid)

    def discard(self, nid: str) -> None:
        self._sizes.pop(nid, None)

    def victims(self) -> list[str]:
        """Least recently used unpinned results to free until the total fits the budget."""
        over = self.total - self.budget
        out = []
        for nid, size in self._sizes.items():
            if over <= 0:
                break
            if nid not in self.pinned:
                out.append(nid)
                over -= size
        return out
