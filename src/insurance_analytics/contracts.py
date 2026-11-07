"""Data contracts shared by batch jobs and interactive consumers."""

from collections.abc import Iterable

import numpy as np
import pandas as pd


def require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Input must contain at least one row")


def finite(frame: pd.DataFrame, columns: Iterable[str], *, nonnegative: bool = False) -> None:
    columns = list(columns)
    require_columns(frame, columns)
    values = frame[columns].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"Non-finite values in {columns}")
    if nonnegative and (values < 0).any():
        raise ValueError(f"Negative values in {columns}")


def unique(frame: pd.DataFrame, keys: list[str]) -> None:
    require_columns(frame, keys)
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"Keys must be unique and non-null: {keys}")


def binary(frame: pd.DataFrame, column: str) -> None:
    finite(frame, [column])
    if not frame[column].isin([0, 1]).all():
        raise ValueError(f"{column} must contain only 0 and 1")
