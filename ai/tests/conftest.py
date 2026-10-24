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


@pytest.fixture
def target(target_id):
    """The same random job target, under the shorter name some tests use."""
    return target_id


@pytest.fixture
def base_env():
    """A complete, valid set of settings (no real keys)."""
    return {
        "DATABASE_URL": "postgres://u:p@h:5432/d",
        "S3_ENDPOINT": "http://s3:9000",
        "S3_REGION": "auto",
        "S3_BUCKET": "talnex",
        "S3_ACCESS_KEY": "a",
        "S3_SECRET_KEY": "b",
        "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        "TINYFISH_AGENT_BASE_URL": "https://agent.tinyfish.ai",
        "TINYFISH_BROWSER_BASE_URL": "https://api.browser.tinyfish.ai",
        "TINYFISH_FETCH_BASE_URL": "https://api.fetch.tinyfish.ai",
        "AGENTMAIL_BASE_URL": "https://api.agentmail.to",
    }
