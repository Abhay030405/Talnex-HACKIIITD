"""Live events: what TalNex is doing right now, streamed as it happens (docs/live_events.md).

Workers send small events through Postgres's own message channel; the Go API forwards them to the
website as a live stream. Sending an event can never break or slow down a check.
"""
from talnex_ai.live.events import CHANNEL, Emitter, NullEmitter, OnEvent, for_job

__all__ = ["CHANNEL", "Emitter", "NullEmitter", "OnEvent", "for_job"]
