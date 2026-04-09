from typing import Dict, List

import requests

from .config import Settings


class OpenAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_reply(self, messages: List[Dict[str, str]]) -> str:
        payload = {
            "model": self.settings.openai_model,
            "input": [
                {
                    "role": item["role"],
                    "content": [{"type": "input_text", "text": item["content"]}],
                }
                for item in messages
            ],
        }
        response = requests.post(
            self.settings.openai_base_url + "/responses",
            headers={
                "Authorization": "Bearer " + self.settings.openai_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        text = self._extract_text(data)
        if not text:
            raise RuntimeError("OpenAI response did not contain readable text: %s" % data)
        return text.strip()

    @staticmethod
    def _extract_text(data: Dict[str, object]) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct

        parts: List[str] = []
        output = data.get("output", [])
        if not isinstance(output, list):
            return ""

        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
                if isinstance(text, dict):
                    nested = text.get("value")
                    if isinstance(nested, str):
                        parts.append(nested)
        return "\n".join(part for part in parts if part).strip()
