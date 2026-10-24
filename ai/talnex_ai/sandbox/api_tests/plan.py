"""HTTP test plans for a backend running in a VM (architecture 28.7), and the plans that need no model.

A plan is a short list of requests with what each answer must look like. Code runs them and checks the answers, so a run is
the same every time. A model writes the plans that need to understand the project (the normal use of a feature, a known
answer); everything else is built here from the routes:

  route smoke   every route answers without a server error
  edge cases    empty body, a missing field, wrong types, a very long value, odd characters, bad JSON, a bad id
  access        a protected route turns away a missing or a bad token
  light load    ten requests at once do not crash the app

Anything that is only our guess about the project (a route that may not exist, a route that may need a sign-in) is marked
"soft": if the answer looks like that, the result is "could not confirm", never a mark against the project.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from talnex_ai.formats import TestType

Method = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
WRITE_METHODS = ("POST", "PUT", "PATCH")
MAX_BODY_CHARS = 20_000
# The most characters the "very long value" step may send in total, shared between the fields, so a route with several
# fields stays under MAX_BODY_CHARS. Each field still gets well over a thousand characters.
LONG_VALUE_TOTAL_CHARS = 15_000
LONG_VALUE_MAX_CHARS = 5_000
MAX_STEPS = 24
MAX_PARALLEL = 20
BAD_TOKEN = "talnex-invalid-token"
_PARAM = re.compile(r"\{[^}/]*\}|:[A-Za-z_]\w*|<[^>/]*>|\[[^\]/]*\]")
_VAR = re.compile(r"\{([A-Za-z_]\w*)\}")


class HttpStep(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    method: Method = "GET"
    path: str = Field(min_length=1, max_length=400)          # may use {name} for a value captured by an earlier step
    headers: dict[str, str] = Field(default_factory=dict)
    json_body: Optional[Any] = None
    raw_body: Optional[str] = Field(default=None, max_length=MAX_BODY_CHARS)
    # What a good answer is. An empty list means "any 2xx" unless expect_below is given.
    expect_status: list[int] = Field(default_factory=list, max_length=12)
    expect_below: Optional[int] = Field(default=None, ge=100, le=600)       # the status must be lower than this
    # Statuses that mean "we could not confirm" (a route that may not exist, a sign-in we do not have), not "failed".
    soft_status: list[int] = Field(default_factory=list, max_length=12)
    expect_contains: list[str] = Field(default_factory=list, max_length=8)  # each must appear in the body, ignoring case
    expect_json_keys: list[str] = Field(default_factory=list, max_length=12)  # these keys must exist (in the object, or the first item of a list)
    capture: dict[str, str] = Field(default_factory=dict, max_length=6)    # name -> dotted path in the JSON answer, e.g. "data.id"
    parallel: int = Field(default=1, ge=1, le=MAX_PARALLEL)                 # send this many copies at once
    # True = send this request exactly as written, WITHOUT the sign-in token a run may have obtained (access tests do this on purpose).
    anonymous: bool = False
    # HTTP Basic sign-in: {"username": "...", "password": "..."} (values may use {run}). The runner builds the Authorization header,
    # which a plan cannot do itself because it needs the two joined and encoded.
    basic_auth: Optional[dict[str, str]] = None
    note: str = Field(default="", max_length=200)

    @field_validator("path")
    @classmethod
    def _path_is_a_path(cls, v: str) -> str:
        if not v.startswith("/") or re.search(r"\s", v):
            raise ValueError("path must start with / and contain no spaces")
        return v

    @model_validator(mode="after")
    def _safe(self) -> "HttpStep":
        # Deleting is only allowed for something this plan made (its id was captured), never a whole collection.
        if self.method == "DELETE" and not _VAR.search(self.path):
            raise ValueError("a DELETE must name a record this plan created (a path with a captured {id})")
        if self.json_body is not None and self.raw_body is not None:
            raise ValueError("give json_body or raw_body, not both")
        if self.basic_auth is not None and set(self.basic_auth) != {"username", "password"}:
            raise ValueError("basic_auth needs exactly a username and a password")
        if self.json_body is not None and len(repr(self.json_body)) > MAX_BODY_CHARS:
            raise ValueError("the body is too big")
        return self


class HttpPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_id: Optional[str] = None
    test_type: TestType
    steps: list[HttpStep] = Field(min_length=1, max_length=MAX_STEPS)
    expected_result: str = Field(min_length=3, max_length=400)


# ---------------------------------------------------------------- helpers


def concrete_path(path: str, value: str = "1") -> str:
    """A route path with every parameter (:id, {id}, <int:id>) filled with a value."""
    return _PARAM.sub(value, path) or "/"


def has_params(path: str) -> bool:
    return bool(_PARAM.search(path))


def sample_body(fields: Sequence[str]) -> dict[str, str]:
    """A plausible body: each field is a short text labelled as test data."""
    return {f: f"TalNex test {f}" for f in fields} if fields else {}


def _method(route_method: str) -> str:
    return "GET" if route_method == "ANY" else route_method


# ---------------------------------------------------------------- plans that need no model


def smoke_plan(method: str, path: str, body_fields: Sequence[str] = ()) -> Optional[HttpPlan]:
    """The route answers without a server error. A 404 or 405 might be our own mistake in finding the route, so it is soft
    (and soft statuses are checked first).
    Deleting routes are not tried: the plan cannot know what a delete would remove."""
    method = _method(method)
    if method == "DELETE":
        return None
    write = method in WRITE_METHODS
    step = HttpStep(
        method=method, path=concrete_path(path), json_body=(sample_body(body_fields) if write else None),
        expect_below=500, soft_status=[404, 405], note="the route answers a normal request",
    )
    return HttpPlan(test_type="route_smoke", steps=[step], expected_result=f"{method} {path} answers without a server error")


def collection_path(path: str) -> str:
    """The path up to the first parameter: /api/books/:id/rating -> /api/books. A record is made by posting here."""
    keep: list[str] = []
    for piece in path.strip("/").split("/"):
        if _PARAM.fullmatch(piece):
            break
        keep.append(piece)
    return "/" + "/".join(keep)


def edge_plan(method: str, path: str, body_fields: Sequence[str] = (), needs_auth: Optional[bool] = None,
              record_source: Optional[tuple[str, Sequence[str]]] = None) -> Optional[HttpPlan]:
    """Bad input to a route that takes a body or an id. Every step passes when the app answers without a server error:
    a polite 4xx is the good outcome and a crash (5xx) is the defect. A sign-in wall or a missing route hides what we want
    to see, so those answers are soft (unconfirmed), checked before anything else."""
    method = _method(method)
    steps: list[HttpStep] = []
    url = concrete_path(path)
    if record_source and has_params(path):
        # A route about one record must be tried on a record that exists, or the app answers "not found" before it reaches the
        # code that handles the input. So a record is made first through the collection's POST route, and its id is used.
        source_path, source_fields = record_source
        steps.append(HttpStep(method="POST", path=concrete_path(source_path), json_body=sample_body(source_fields), expect_below=500,
                              soft_status=[401, 403, 404, 405], capture={"rid": "id|_id|data.id|uuid|pk"},
                              note="make a record the next steps can use"))
        url = concrete_path(path, "{rid}")

    def add(note: str, soft: Sequence[int] = (401, 403, 404, 405), **kw: Any) -> None:
        steps.append(HttpStep(method=method, path=kw.pop("path", url), expect_below=500, soft_status=list(soft), note=note, **kw))

    if method in WRITE_METHODS:
        fields = list(body_fields)[:4]
        add("an empty JSON body", json_body={})
        for f in fields[:3]:
            add(f"the field {f} is missing", json_body={k: f"TalNex test {k}" for k in fields if k != f})
        if fields:
            add("every field is a number", json_body={k: 12345 for k in fields})
            add("every field is plain text where a number may be expected", json_body={k: "abc" for k in fields})
            add("every field is an object", json_body={k: {"a": 1} for k in fields})
            add("every field is null", json_body={k: None for k in fields})
            long_value = "A" * min(LONG_VALUE_MAX_CHARS, LONG_VALUE_TOTAL_CHARS // len(fields))
            add("a very long value", json_body={k: long_value for k in fields})
            add("quotes, tags and odd characters", json_body={k: "TalNex test ' \" <script>alert(1)</script> \\ é中 -- ;" for k in fields})
        else:
            add("a very long value", json_body={"value": "A" * LONG_VALUE_MAX_CHARS})
            add("odd characters", json_body={"value": "TalNex test ' \" <b>x</b> é中"})
        add("a body that is not JSON", raw_body="this is not json {", headers={"Content-Type": "application/json"})
        add("an array where an object is expected", json_body=[1, 2, 3])
    if has_params(path):
        for label, value in (("an id that does not exist", "999999999"), ("an id that is text", "abc"), ("a negative id", "-1")):
            # A 404 is the right answer for an id that does not exist, so only a sign-in wall or a wrong method is "unconfirmed".
            add(f"{label}", soft=(401, 403, 405), path=concrete_path(path, value),
                **({"json_body": sample_body(body_fields)} if method in WRITE_METHODS else {}))
    if not steps:
        return None
    return HttpPlan(test_type="edge_case", steps=steps[:MAX_STEPS],
                    expected_result=f"{method} {path} answers every bad input without a server error")


def access_plan(routes: Sequence[tuple[str, str, Sequence[str]]]) -> Optional[HttpPlan]:
    """Routes that look protected turn away a request with no token and one with a wrong token. `routes` is (method, path, fields)."""
    steps: list[HttpStep] = []
    for method, path, fields in routes[:8]:
        method = _method(method)
        body = sample_body(fields) if method in WRITE_METHODS else None
        for label, headers in (("no token", {}), ("a wrong token", {"Authorization": f"Bearer {BAD_TOKEN}"})):
            steps.append(HttpStep(method=method, path=concrete_path(path), headers=headers, json_body=body, anonymous=True,
                                  expect_status=[401, 403], soft_status=[404, 405], note=f"{method} {path} with {label}"))
    if not steps:
        return None
    return HttpPlan(test_type="access", steps=steps[:MAX_STEPS],
                    expected_result="every protected route turns away a request with no token or a wrong token")


def load_plan(path: str) -> HttpPlan:
    """Ten requests at once, then one more to see the app still answers."""
    return HttpPlan(
        test_type="light_load",
        steps=[HttpStep(method="GET", path=path, expect_below=500, parallel=10, note="ten requests at the same time"),
               HttpStep(method="GET", path=path, expect_below=500, note="the app still answers afterwards")],
        expected_result="the app answers ten simultaneous requests and is still up afterwards")


def with_label(plan: HttpPlan, claim_id: Optional[str]) -> HttpPlan:
    return plan.model_copy(update={"claim_id": claim_id})
