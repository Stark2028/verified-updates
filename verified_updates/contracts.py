"""Shared data contracts; UI and lab consume real client outcomes."""

from dataclasses import asdict, dataclass
import re
from pathlib import PurePosixPath
from typing import Any


class UpdateError(Exception):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise UpdateError("INVALID_INPUT", "Identifiers must use lowercase letters, digits, underscores or hyphens.")
    return value


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise UpdateError("INVALID_PACKAGE", "Package paths must be relative POSIX paths.")
    parts = value.split("/")
    if PurePosixPath(value).is_absolute() or any(x in ("", ".", "..") for x in parts):
        raise UpdateError("INVALID_PACKAGE", f"Unsafe package path: {value!r}")
    return value


@dataclass(frozen=True)
class Release:
    app_id: str
    platform: str
    version: str
    sequence: int
    entrypoint: str = "app.py"

    def __post_init__(self) -> None:
        identifier(self.app_id)
        identifier(self.platform)
        if type(self.sequence) is not int or self.sequence < 1:
            raise UpdateError("INVALID_INPUT", "Release sequence must be a positive integer.")
        if not isinstance(self.version, str) or not self.version or len(self.version) > 64:
            raise UpdateError("INVALID_INPUT", "Display version must contain 1-64 characters.")
        relative_path(self.entrypoint)
        if not self.entrypoint.endswith(".py"):
            raise UpdateError("INVALID_PACKAGE", "This first installer supports Python entrypoints only.")

    @property
    def target_path(self) -> str:
        return f"apps/{self.app_id}/{self.platform}/application.zip"

    def to_custom(self) -> dict[str, Any]:
        return {"verified_updates": {"schema_version": 1, **asdict(self)}}

    @classmethod
    def from_custom(cls, custom: dict[str, Any]) -> "Release":
        data = custom.get("verified_updates") if isinstance(custom, dict) else None
        fields = {"schema_version", "app_id", "platform", "version", "sequence", "entrypoint"}
        if not isinstance(data, dict) or set(data) != fields or type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise UpdateError("INVALID_RELEASE_METADATA", "Unknown or malformed signed release schema.")
        return cls(**{key: value for key, value in data.items() if key != "schema_version"})


@dataclass
class UpdateResult:
    run_id: str
    app_id: str
    outcome: str
    reason_code: str
    detail: str
    installed_before: int | None
    installed_after: int | None
    version: str | None = None
    stage: str = "initializing"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

