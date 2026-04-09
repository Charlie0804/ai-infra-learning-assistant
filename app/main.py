import json
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request

from .agent import AgentService
from .config import load_settings
from .db import BotDB
from .feishu import FeishuClient
from .openai_client import OpenAIClient
from .tools import RepoTools


settings = load_settings()
db = BotDB(settings.data_dir / "bot.db")
repo_tools = RepoTools(settings)
openai_client = OpenAIClient(settings)
agent_service = AgentService(settings, db, repo_tools, openai_client)
feishu_client = FeishuClient(settings)

app = FastAPI(title="Feishu SGLang Bot")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "missing": settings.runtime_missing,
        "sglang_repo": str(settings.sglang_repo),
        "data_dir": str(settings.data_dir),
    }


@app.post("/webhook/feishu/events")
async def handle_feishu_events(request: Request) -> Dict[str, Any]:
    body = await request.json()
    payload = _unwrap_payload(body)

    if payload.get("type") == "url_verification" and payload.get("challenge"):
        _verify_token(payload)
        return {"challenge": payload["challenge"]}

    header = payload.get("header", {})
    if not isinstance(header, dict):
        header = {}

    event_type = header.get("event_type")
    if event_type != "im.message.receive_v1":
        return {"code": 0, "msg": "ignored"}

    _verify_token(payload)

    event_id = str(header.get("event_id", ""))
    if event_id and not db.mark_event_processed(event_id):
        return {"code": 0, "msg": "duplicate"}

    event = payload.get("event", {})
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Invalid event payload")

    message = event.get("message", {})
    sender = event.get("sender", {})
    if not isinstance(message, dict) or not isinstance(sender, dict):
        raise HTTPException(status_code=400, detail="Missing message or sender")

    if str(sender.get("sender_type", "")).lower() == "app":
        return {"code": 0, "msg": "self message ignored"}

    if message.get("message_type") != "text":
        return _reply_with_text(message, "当前 MVP 先只处理文本消息。")

    user_id = _extract_sender_id(sender)
    chat_id = str(message.get("chat_id", "")).strip()
    text = _extract_text_content(message.get("content", ""))

    if not user_id or not chat_id:
        raise HTTPException(status_code=400, detail="Missing user_id or chat_id")

    if not text:
        return _reply_with_text(message, "我收到了空消息，可以直接发源码问题或者 `/help`。")

    if settings.runtime_missing:
        return _reply_with_text(
            message,
            "服务配置还没填完，缺少：{0}".format(", ".join(settings.runtime_missing)),
        )

    try:
        reply = agent_service.handle_message(user_id=user_id, chat_id=chat_id, text=text)
    except Exception as exc:
        reply = "处理这条消息时出错了：{0}".format(exc)

    feishu_client.send_text(chat_id, reply)
    return {"code": 0}


def _unwrap_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    if "encrypt" in body:
        raise HTTPException(
            status_code=400,
            detail="This MVP does not yet support Feishu encrypted callbacks. Disable event encryption first.",
        )
    return body


def _verify_token(payload: Dict[str, Any]) -> None:
    candidates = []
    if payload.get("token"):
        candidates.append(str(payload["token"]))
    header = payload.get("header", {})
    if isinstance(header, dict) and header.get("token"):
        candidates.append(str(header["token"]))

    if candidates and settings.feishu_verification_token not in candidates:
        raise HTTPException(status_code=403, detail="Verification token mismatch")


def _extract_sender_id(sender: Dict[str, Any]) -> str:
    sender_id = sender.get("sender_id", {})
    if not isinstance(sender_id, dict):
        return ""
    for key in ("open_id", "user_id", "union_id"):
        value = sender_id.get(key)
        if value:
            return str(value)
    return ""


def _extract_text_content(raw_content: Any) -> str:
    if isinstance(raw_content, dict):
        return str(raw_content.get("text", "")).strip()
    if isinstance(raw_content, str):
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError:
            return raw_content.strip()
        return str(data.get("text", "")).strip()
    return ""


def _reply_with_text(message: Dict[str, Any], text: str) -> Dict[str, Any]:
    chat_id = str(message.get("chat_id", "")).strip()
    if chat_id:
        feishu_client.send_text(chat_id, text)
    return {"code": 0}
