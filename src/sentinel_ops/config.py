"""Explicit configuration; external writes cannot be enabled in this build."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    mode: Literal["local"] = "local"
    payment_enabled: Literal[False] = False
    sandbox_auto_merge: Literal[False] = False
    external_writes: Literal[False] = False
    timeout_seconds: float = Field(default=3, gt=0, le=10)
    max_response_bytes: int = Field(default=4096, ge=128, le=65536)
    max_patch_bytes: int = Field(default=16384, ge=1, le=65536)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database: Path = Path(".local/investigations.sqlite")

    def confined_database(self, root: Path) -> Path:
        target = (root / self.database).resolve()
        if not target.is_relative_to(root.resolve() / ".local"):
            raise ValueError("Database must be inside repository .local directory")
        return target
