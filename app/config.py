import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional before deps are installed
    def load_dotenv(*_args, **_kwargs):
        return False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass
class Settings:
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_verification_token: str
    feishu_encrypt_key: str
    feishu_base_url: str
    sglang_repo: Path
    sglang_notes_root: Path
    data_dir: Path
    host: str
    port: int
    history_window: int
    code_search_limit: int
    snippet_context_lines: int

    @property
    def runtime_missing(self) -> List[str]:
        missing = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.feishu_app_id:
            missing.append("FEISHU_APP_ID")
        if not self.feishu_app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not self.feishu_verification_token:
            missing.append("FEISHU_VERIFICATION_TOKEN")
        if not self.sglang_repo.exists():
            missing.append("SGLANG_REPO")
        return missing


def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        feishu_app_id=os.getenv("FEISHU_APP_ID", "").strip(),
        feishu_app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
        feishu_verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", "").strip(),
        feishu_encrypt_key=os.getenv("FEISHU_ENCRYPT_KEY", "").strip(),
        feishu_base_url=os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/"),
        sglang_repo=Path(os.getenv("SGLANG_REPO", str(PROJECT_ROOT.parent / "sglang"))).resolve(),
        sglang_notes_root=Path(
            os.getenv("SGLANG_NOTES_ROOT", str(PROJECT_ROOT / "notes"))
        ).resolve(),
        data_dir=Path(os.getenv("BOT_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve(),
        host=os.getenv("HOST", "0.0.0.0").strip(),
        port=_int_env("PORT", 8000),
        history_window=_int_env("HISTORY_WINDOW", 8),
        code_search_limit=_int_env("CODE_SEARCH_LIMIT", 6),
        snippet_context_lines=_int_env("SNIPPET_CONTEXT_LINES", 18),
    )
