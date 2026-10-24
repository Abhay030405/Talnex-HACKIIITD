import os
import uuid

import pytest

TEST_DB_ENV = "TALNEX_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def db_pool():
    """A pool on a separate test database with the migrations applied. Skips when none is set up.

    Never point this at a real database: the tests empty the jobs table."""
    url = os.environ.get(TEST_DB_ENV, "").strip()
    if not url:
        pytest.skip(f"{TEST_DB_ENV} is not set")
    from talnex_ai.db import open_pool

    pool = open_pool(url, max_size=4)
    yield pool
    pool.close()


@pytest.fixture
def pool(db_pool):
    with db_pool.connection() as conn:
        conn.execute("DELETE FROM usage_log")
        conn.execute("DELETE FROM jobs")
    return db_pool


@pytest.fixture
def target_id():
    return str(uuid.uuid4())
