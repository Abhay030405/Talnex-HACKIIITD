"""The run recipe: everything needed to build and start a repo in a VM (architecture section 28.5).

Stack detect writes it before anything is built, and it is saved with the run (`sandbox_runs.recipe`), so a reader can
see exactly what was tried and where each choice came from."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Stack = Literal["node", "python", "unknown"]
Source = Literal["compose", "dockerfile", "readme", "package_files", "model_guess", "model_fix"]
Confidence = Literal["high", "medium", "low"]

# The base image that runs each stack (sandbox/images). Node and Python share one image, so a repo needs one VM
# whatever it is built with. Stacks that need their own image (Go, Java, compose) get an entry here when it is built.
FULL_IMAGE = "talnex-sandbox-full"
IMAGES: dict[str, str] = {"node": FULL_IMAGE, "python": FULL_IMAGE}


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stack: Stack
    image: str = ""
    # Folder of the app inside the cloned repo ("" = the repo root). A repo with client/ and server/ runs the server.
    app_dir: str = ""
    install_cmd: str = ""
    build_cmd: str = ""
    start_cmd: str = ""
    # The port the app is expected to listen on. None = use whatever port it opens.
    port: Optional[int] = None
    health_paths: list[str] = Field(default_factory=lambda: ["/", "/health", "/api/health", "/healthz"])
    env: dict[str, str] = Field(default_factory=dict)
    # Things the app needs that are not in the VM image (postgres, redis, mongodb, ...). Empty = nothing else needed.
    services: list[str] = Field(default_factory=list)
    # The repo's own test command, run later as evidence.
    test_cmd: str = ""
    source: Source = "package_files"
    confidence: Confidence = "medium"
    notes: list[str] = Field(default_factory=list)

    def with_note(self, note: str) -> "Recipe":
        return self.model_copy(update={"notes": [*self.notes, note]})
