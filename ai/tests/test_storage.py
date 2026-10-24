import os
import uuid

import pytest

from talnex_ai.settings import S3Settings
from talnex_ai.storage import Store, keys


@pytest.fixture
def store():
    endpoint = os.environ.get("TALNEX_TEST_S3_ENDPOINT", "").strip()
    if not endpoint:
        pytest.skip("TALNEX_TEST_S3_ENDPOINT is not set")
    s = Store(S3Settings(endpoint, "us-east-1", "talnex-test",
                         os.environ["TALNEX_TEST_S3_ACCESS_KEY"], os.environ["TALNEX_TEST_S3_SECRET_KEY"]))
    s.ensure_bucket()
    return s


def test_keys_match_the_go_layout():
    assert keys.screen_key("p1", "r1", 3) == "screens/p1/r1/3"
    assert keys.video_key("p1", "demo.mp4") == "videos/p1/demo.mp4"
    assert keys.frame_key("p1", "0007.jpg") == "frames/p1/0007.jpg"
    assert keys.resume_key("c1", "cv.pdf") == "resumes/c1/cv.pdf"
    assert keys.resume_prefix("c1") == "resumes/c1/"
    assert keys.replay_key("c1", "weekly-400", "two-sum") == "replays/c1/weekly-400/two-sum"
    assert keys.sandbox_key("p1", "r1", "tests.log") == "sandbox/p1/r1/tests.log"
    assert keys.voice_key("u1", "w1") == "voice/u1/w1"
    assert keys.opinion_key("p1", "home.png") == "opinion/p1/home.png"


@pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "a\\b", "../../secrets"])
def test_keys_refuse_parts_that_escape_their_folder(bad):
    with pytest.raises(ValueError):
        keys.sandbox_key("p1", "r1", bad)


@pytest.mark.parametrize("endpoint", ["s3:9000", "", "ftp://s3:9000"])
def test_store_wants_a_full_endpoint(endpoint):
    with pytest.raises(ValueError, match="S3_ENDPOINT"):
        Store(S3Settings(endpoint, "auto", "b", "k", "s"))


def test_put_get_exists_delete(store):
    key = keys.screen_key("p-" + uuid.uuid4().hex[:8], "r1", 2)
    assert not store.exists(key)
    store.put_bytes(key, b"proof", "text/plain")
    assert store.exists(key)
    assert store.get_bytes(key) == b"proof"
    store.delete(key)
    assert not store.exists(key)
    store.delete(key)
