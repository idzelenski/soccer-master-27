from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    club_target: int = max(100, min(1000, int(os.getenv("SM27_CLUB_TARGET", "750"))))
    session_days: int = 14


settings = Settings()
