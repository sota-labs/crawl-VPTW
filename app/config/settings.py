import os
from pathlib import Path

from datetime import datetime

from dotenv import load_dotenv

from app.config.logging import log
from app.shares.base.singleton import SingletonBase

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))


class AppSettings(SingletonBase):
    def __init__(self):
        self._load_environment()
        self._load_config()

    def _load_environment(self):
        base_dir = Path(__file__).resolve().parent.parent.parent
        env = os.getenv("APP_ENV", "dev")
        env_file = base_dir / f".env.{env}"

        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=True)
            log.info(f"Loaded environment from {env_file}")
        else:
            fallback = base_dir / ".env"
            load_dotenv(dotenv_path=fallback, override=True)
            log.warning(f"{env_file} not found. Loaded fallback: {fallback}")

    def _load_config(self):
        # server config
        self.APP_NAME = os.getenv("APP_NAME", "shared-org-customer")
        self.PORT = int(os.getenv("PORT", 8000))
        self.PREFIX = "/api/v1"
        self.DEBUG = os.getenv("DEBUG", "false").lower() == "true"
        self.HOST = os.getenv("HOST", "localhost")

        self.MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
        if not self.MISTRAL_API_KEY:
            raise ValueError("MISTRAL_API_KEY environment variable is required")

        self.VPTW_BASE_URL: str = os.getenv("VPTW_BASE_URL", "")
        if not self.VPTW_BASE_URL:
            raise ValueError("VPTW_BASE_URL environment variable is required")
        
        self.ORG_ID: str = os.getenv("ORG_ID", "")
        self.CHATBOT_ID: str = os.getenv("CHATBOT_ID", "")
        self.VALID_DATE_FROM: datetime = datetime.strptime(os.getenv("VALID_DATE_FROM", ""), "%d/%m/%Y").date()

settings = AppSettings()
