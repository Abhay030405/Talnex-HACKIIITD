"""The live screen: frames are acknowledged, only the newest is published, and a browser without CDP is fine."""
import base64
import time

from talnex_ai.testing.runner import screencast


class FakeCDP:
    def __init__(self):
        self.sent, self.handlers = [], {}

    def on(self, name, fn):
        self.handlers[name] = fn

    def send(self, method, params=None):
        self.sent.append(method)


class FakePage:
    def __init__(self, cdp):
        self.context = type("Ctx", (), {"new_cdp_session": lambda _self, page: cdp})()


def test_frames_are_acked_and_the_newest_is_published():
    cdp, got = FakeCDP(), []
    live = screencast.start(type("D", (), {"page": FakePage(cdp)})(), got.append, fps=20, quality=50, width=960)
    for n in range(3):
        cdp.handlers["Page.screencastFrame"]({"sessionId": n, "data": base64.b64encode(f"f{n}".encode()).decode()})
    time.sleep(0.2)
    live.stop()
    assert cdp.sent.count("Page.screencastFrameAck") == 3 and "Page.stopScreencast" in cdp.sent
    assert got == [b"f2"]


def test_no_page_or_fps_zero_means_no_screencast():
    assert screencast.start(object(), print, fps=2, quality=50, width=960) is None
    assert screencast.start(type("D", (), {"page": FakePage(FakeCDP())})(), print, fps=0, quality=50, width=960) is None
