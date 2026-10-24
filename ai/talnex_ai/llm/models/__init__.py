"""Which model plays which role. The roles are fixed (architecture section 19); the model for
each comes from settings and is picked by testing, never typed into code."""
from __future__ import annotations

from talnex_ai.settings import MODEL_ROLES, LLMSettings, SettingsError

ROLES = tuple(MODEL_ROLES)


def check_role(role: str) -> None:
    if role not in MODEL_ROLES:
        raise ValueError(f"unknown model role {role!r}; the roles are {', '.join(ROLES)}")


def model_for(cfg: LLMSettings, role: str) -> str:
    """The model name for a role, or an error naming the setting to fill in."""
    check_role(role)
    model = cfg.models.get(role, "")
    if not model:
        raise SettingsError(f"{MODEL_ROLES[role]} is not set (the model for the '{role}' job)")
    return model
