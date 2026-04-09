import json
import time
from typing import Iterable, List, Optional

import requests

from .config import Settings


class FeishuClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: Optional[str] = None
        self._token_expire_at = 0.0

    def _get_tenant_access_token(self) -> str:
        if self._token and time.time() < self._token_expire_at:
            return self._token

        response = requests.post(
            self.settings.feishu_base_url + "/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.settings.feishu_app_id,
                "app_secret": self.settings.feishu_app_secret,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError("Failed to get tenant_access_token: %s" % payload)
        self._token = payload["tenant_access_token"]
        expire = int(payload.get("expire", 7200))
        self._token_expire_at = time.time() + max(expire - 120, 60)
        return self._token

    def send_text(self, chat_id: str, text: str) -> None:
        token = self._get_tenant_access_token()
        for chunk in self._split_text(text):
            response = requests.post(
                self.settings.feishu_base_url
                + "/open-apis/im/v1/messages?receive_id_type=chat_id",
                headers={"Authorization": "Bearer " + token},
                json={
                    "receive_id": chat_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": chunk}, ensure_ascii=False),
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise RuntimeError("Failed to send Feishu message: %s" % payload)

    @staticmethod
    def _split_text(text: str, chunk_size: int = 1600) -> Iterable[str]:
        if len(text) <= chunk_size:
            return [text]

        chunks: List[str] = []
        current = ""
        for line in text.splitlines(keepends=True):
            if len(current) + len(line) > chunk_size and current:
                chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)
        return chunks
