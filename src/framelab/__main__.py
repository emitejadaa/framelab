"""``python -m framelab datos.csv`` — open a file in the workbench."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .naming import RootSpec, sanitize_identifier, unique_name

READERS = {
    ".csv": pd.read_csv,
    ".tsv": lambda p: pd.read_csv(p, sep="\t"),
    ".txt": pd.read_csv,
    ".parquet": pd.read_parquet,
    ".json": pd.read_json,
    ".xlsx": pd.read_excel,
    ".xls": pd.read_excel,
    ".feather": pd.read_feather,
    ".pkl": None,  # never unpickle files from the command line
}


def load_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        supported = ", ".join(k for k, v in READERS.items() if v is not None)
        raise SystemExit(f"framelab: cannot open {path.name} (supported: {supported})")
    return reader(path)


def variable_name(path: str | Path) -> str:
    return sanitize_identifier(Path(path).stem)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="framelab", description="Explore a data file.")
    parser.add_argument("files", nargs="+", help="CSV, TSV, Parquet, JSON, Excel or Feather files")
    args = parser.parse_args(argv)
    from . import api
    from .session import Session

    roots: list[RootSpec] = []
    for f in args.files:  # a unique variable per file, even when two names clean up the same
        name = unique_name(variable_name(f), {r.name for r in roots})
        roots.append(RootSpec(name, load_table(f)))
    session = Session(roots, api.registry)
    api._start_autosave(session)
    api._show(session, None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
