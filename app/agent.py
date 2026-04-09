from typing import Dict, List

from .config import Settings
from .db import BotDB
from .openai_client import OpenAIClient
from .tools import LocalCommandHandler, RepoTools


SYSTEM_PROMPT = """你是一个中文的 AI Infra 源码学习助手，工作在飞书聊天里。

目标：
1. 帮用户理解当前配置到本地仓库里的源码。
2. 结合本地任务和学习笔记，持续推进源码阅读。
3. 回答尽量准确，优先使用提供的本地代码检索上下文。

回答规则：
- 默认使用中文。
- 当你引用代码时，优先给出相对路径和行号。
- 如果上下文不足，请明确说“当前检索到的证据不足”，然后告诉用户下一步该搜什么。
- 保持高信息密度，但不要无意义展开。
- 如果用户在问今天任务、未完成事项或学习计划，请结合任务快照回答。
"""


class AgentService:
    def __init__(
        self,
        settings: Settings,
        db: BotDB,
        repo_tools: RepoTools,
        openai_client: OpenAIClient,
    ) -> None:
        self.settings = settings
        self.db = db
        self.repo_tools = repo_tools
        self.command_handler = LocalCommandHandler(db, repo_tools)
        self.openai_client = openai_client

    def handle_message(self, user_id: str, chat_id: str, text: str) -> str:
        local_reply = self.command_handler.maybe_handle(user_id, text)
        self.db.add_message(user_id, chat_id, "user", text)
        if local_reply is not None:
            self.db.add_message(user_id, chat_id, "assistant", local_reply)
            return local_reply

        messages = self._build_prompt_messages(user_id, text)
        reply = self.openai_client.generate_reply(messages)
        self.db.add_message(user_id, chat_id, "assistant", reply)
        return reply

    def _build_prompt_messages(self, user_id: str, latest_text: str) -> List[Dict[str, str]]:
        recent_messages = self.db.get_recent_messages(user_id, self.settings.history_window)
        task_rows = self.db.list_tasks(user_id)
        note_rows = self.db.recent_notes(user_id, limit=5)
        code_context = self.repo_tools.build_context(latest_text)

        task_snapshot = "\n".join(
            "#{0} {1}".format(row["id"], row["description"]) for row in task_rows[:10]
        )
        if not task_snapshot:
            task_snapshot = "当前没有未完成任务。"

        note_snapshot = "\n".join(
            "#{0} {1}".format(row["id"], row["content"]) for row in reversed(note_rows)
        )
        if not note_snapshot:
            note_snapshot = "当前没有学习笔记。"

        context_block = (
            "【用户未完成任务】\n{0}\n\n"
            "【最近学习笔记】\n{1}\n\n"
            "【本轮本地检索上下文】\n{2}"
        ).format(task_snapshot, note_snapshot, code_context or "没有命中到直接代码片段。")

        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.append({"role": "system", "content": context_block})
        for item in recent_messages:
            messages.append(
                {
                    "role": item["role"],
                    "content": item["content"][:2000],
                }
            )
        return messages
