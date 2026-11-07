"""Reinsurance premium reporting using integer cents and decimal half-up rounding."""

from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

from .contracts import finite, require_columns, unique


def premium_report(frame: pd.DataFrame) -> pd.DataFrame:
    require_columns(frame, ["accounting_date", "client", "currency", "policy_id"])
    unique(frame, ["transaction_id"])
    finite(frame, ["gross_premium", "ceded_share", "sum_assured"])
    if ((frame.ceded_share < 0) | (frame.ceded_share > 1)).any() or (frame.sum_assured < 0).any():
        raise ValueError("Ceded share must be in [0,1] and sums assured nonnegative")
    if frame[["client", "currency", "policy_id"]].isna().any().any():
        raise ValueError("Reporting dimensions must be non-null")
    if not frame.currency.astype(str).str.fullmatch(r"[A-Z]{3}").all():
        raise ValueError("Use uppercase three-letter currency codes")
    data = frame.copy()
    dates = pd.to_datetime(data.accounting_date, errors="raise")
    if dates.isna().any():
        raise ValueError("Missing accounting date")
    data["month"] = dates.dt.to_period("M").astype(str)

    def cents(value):
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    data["gross_cents"] = data.gross_premium.map(cents)
    data["ceded_cents"] = [
        int((Decimal(g) * Decimal(str(s))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        for g, s in zip(data.gross_cents, data.ceded_share, strict=True)
    ]
    grouped = data.groupby(["month", "client", "currency"], sort=True)
    result = grouped.agg(
        gross_cents=("gross_cents", "sum"),
        ceded_cents=("ceded_cents", "sum"),
        transactions=("transaction_id", "count"),
        policies=("policy_id", "nunique"),
    ).reset_index()
    # Snapshot volume counts each policy once per client/currency/month, using the last transaction.
    snapshots = data.sort_values(["accounting_date", "transaction_id"]).drop_duplicates(
        ["month", "client", "currency", "policy_id"], keep="last"
    )
    volume = (
        snapshots.assign(ceded_volume=snapshots.sum_assured * snapshots.ceded_share)
        .groupby(["month", "client", "currency"])
        .ceded_volume.sum()
        .reset_index()
    )
    result = result.merge(volume, on=["month", "client", "currency"], validate="one_to_one")
    if not np.isfinite(result.ceded_volume).all():
        raise ValueError("Non-finite volume")
    return result
