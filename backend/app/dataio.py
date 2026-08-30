"""Reads the generated CSVs back into a :class:`~app.models.Dataset`."""

from __future__ import annotations

import csv
import datetime as dt
import functools

from .config import (
    ACCOUNTS_CSV,
    BENEFICIARIES_CSV,
    DEVICE_SESSIONS_CSV,
    TRANSACTIONS_CSV,
)
from .models import Account, Beneficiary, Dataset, DeviceSession, Transaction


def _bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def load_dataset() -> Dataset:
    """Load the four tables. Sorted on the way in, so callers get a stable order."""
    with ACCOUNTS_CSV.open(newline="", encoding="utf-8") as handle:
        accounts = [
            Account(
                account_id=row["account_id"],
                name=row["name"],
                open_date=dt.date.fromisoformat(row["open_date"]),
                dormancy_flag=_bool(row["dormancy_flag"]),
                age_band=row["age_band"],
                phone=row["phone"],
                address=row["address"],
                kyc_date=dt.date.fromisoformat(row["kyc_date"]),
                known_suspicious=_bool(row["known_suspicious"]),
                role=row["role"],
            )
            for row in csv.DictReader(handle)
        ]

    with TRANSACTIONS_CSV.open(newline="", encoding="utf-8") as handle:
        transactions = [
            Transaction(
                txn_id=row["txn_id"],
                from_account=row["from_account"],
                to_account=row["to_account"],
                amount=float(row["amount"]),
                timestamp=dt.datetime.fromisoformat(row["timestamp"]),
                channel=row["channel"],
                tag=row["tag"],
            )
            for row in csv.DictReader(handle)
        ]

    with DEVICE_SESSIONS_CSV.open(newline="", encoding="utf-8") as handle:
        sessions = [
            DeviceSession(
                session_id=row["session_id"],
                account=row["account"],
                device_fingerprint=row["device_fingerprint"],
                ip=row["ip"],
                login_result=row["login_result"],
                timestamp=dt.datetime.fromisoformat(row["timestamp"]),
                password_reset_flag=_bool(row["password_reset_flag"]),
            )
            for row in csv.DictReader(handle)
        ]

    with BENEFICIARIES_CSV.open(newline="", encoding="utf-8") as handle:
        beneficiaries = [
            Beneficiary(
                account=row["account"],
                payee=row["payee"],
                added_timestamp=dt.datetime.fromisoformat(row["added_timestamp"]),
            )
            for row in csv.DictReader(handle)
        ]

    accounts.sort(key=lambda a: a.account_id)
    transactions.sort(key=lambda t: (t.timestamp, t.txn_id))
    sessions.sort(key=lambda s: (s.timestamp, s.session_id))
    beneficiaries.sort(key=lambda b: (b.added_timestamp, b.account, b.payee))
    return Dataset(accounts, transactions, sessions, beneficiaries)


@functools.lru_cache(maxsize=1)
def cached_dataset() -> Dataset:
    """Process-wide cache. The dataset is immutable once generated."""
    return load_dataset()
