"""Environment-backed application settings.

SQLite is the local default and does not contain credentials. The same
``DATABASE_URL`` boundary can later point at a managed database without
embedding connection details in source code.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration loaded from environment variables or ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite:///./data/snakebite.db",
        validation_alias="DATABASE_URL",
    )
    player_name: str = Field(default="Player", validation_alias="PLAYER_NAME")

    @property
    def sqlite_path(self) -> str:
        """Return the filesystem path accepted by ``aiosqlite``."""

        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("DATABASE_URL must use the sqlite:/// scheme")

        path = self.database_url[len(prefix) :]
        if not path:
            raise ValueError("DATABASE_URL must include a SQLite path")
        return path
