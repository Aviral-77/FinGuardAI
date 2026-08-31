"""Mutable builder the generator and the typologies write into.

Kept separate from ``generate`` so ``typologies`` can depend on it without a
circular import. Every ``add_*`` method appends in call order; the generator
sorts at the end, so nothing here depends on dict or set iteration order.
"""

from __future__ import annotations

import datetime as dt
import random

from ..models import Account, Beneficiary, DeviceSession, Transaction


class World:
    """Accumulates the four tables while the world is built."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.accounts: list[Account] = []
        self.transactions: list[Transaction] = []
        self.device_sessions: list[DeviceSession] = []
        self.beneficiaries: list[Beneficiary] = []
        self._txn_seq = 0
        self._session_seq = 0
        self._by_id: dict[str, Account] = {}

    # -- accounts ----------------------------------------------------------

    def add_account(self, account: Account) -> Account:
        if account.account_id in self._by_id:
            raise ValueError(f"duplicate account {account.account_id}")
        self.accounts.append(account)
        self._by_id[account.account_id] = account
        return account

    def get(self, account_id: str) -> Account:
        return self._by_id[account_id]

    def exists(self, account_id: str) -> bool:
        return account_id in self._by_id

    # -- transactions ------------------------------------------------------

    def add_txn(
        self,
        from_account: str,
        to_account: str,
        amount: float,
        timestamp: dt.datetime,
        channel: str,
        tag: str = "",
    ) -> Transaction:
        self._txn_seq += 1
        txn = Transaction(
            txn_id=f"TXN{self._txn_seq:06d}",
            from_account=from_account,
            to_account=to_account,
            amount=round(float(amount), 2),
            timestamp=timestamp,
            channel=channel,
            tag=tag,
        )
        self.transactions.append(txn)
        return txn

    # -- device sessions ---------------------------------------------------

    def add_session(
        self,
        account: str,
        device_fingerprint: str,
        ip: str,
        timestamp: dt.datetime,
        login_result: str = "success",
        password_reset_flag: bool = False,
    ) -> DeviceSession:
        self._session_seq += 1
        session = DeviceSession(
            session_id=f"SES{self._session_seq:06d}",
            account=account,
            device_fingerprint=device_fingerprint,
            ip=ip,
            login_result=login_result,
            timestamp=timestamp,
            password_reset_flag=password_reset_flag,
        )
        self.device_sessions.append(session)
        return session

    # -- beneficiaries -----------------------------------------------------

    def add_beneficiary(self, account: str, payee: str, added: dt.datetime) -> Beneficiary:
        beneficiary = Beneficiary(account=account, payee=payee, added_timestamp=added)
        self.beneficiaries.append(beneficiary)
        return beneficiary
