from __future__ import annotations

import pytest

from gadgetgenie.config import Settings
from gadgetgenie.core.executors import SQLiteExecutor
from gadgetgenie.core.offline import OfflineModel
from gadgetgenie.core.service import build_recommender
from gadgetgenie.core.sql_guard import GuardPolicy
from gadgetgenie.etl.seed import write_sqlite
from gadgetgenie.etl.synthetic import generate
from gadgetgenie.schema import enum_values, view_columns


@pytest.fixture(scope="session")
def devices():
    return generate(n_laptops=40, n_phones=30, n_tablets=10, n_watches=10, seed=5)


@pytest.fixture(scope="session")
def db_path(devices, tmp_path_factory):
    return write_sqlite(devices, tmp_path_factory.mktemp("catalogue") / "test.db")


@pytest.fixture()
def executor(db_path):
    return SQLiteExecutor(db_path, timeout_s=2.0)


@pytest.fixture()
def policy():
    return GuardPolicy(views=view_columns(), enums=enum_values(), max_rows=10)


@pytest.fixture()
def settings(db_path):
    return Settings(llm_provider="offline", sqlite_path=str(db_path), fx_rates_to_usd={"USD": 1.0, "INR": 0.012})


@pytest.fixture()
def make_recommender(settings):
    def _make(model=None, **overrides):
        s = Settings(**{**settings.__dict__, **overrides})
        return build_recommender(s, model=model or OfflineModel(s.max_rows), auto_seed=False)

    return _make
