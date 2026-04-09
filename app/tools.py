import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from .config import Settings
from .db import BotDB


COMMON_IDENTIFIERS = {
    "sglang",
    "python",
    "class",
    "function",
    "return",
    "import",
    "from",
    "with",
    "this",
    "that",
    "what",
    "where",
    "when",
    "please",
}


class RepoTools:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repo_root = settings.sglang_repo
        self.notes_root = settings.sglang_notes_root

    def search_repo(self, query: str, limit: Optional[int] = None) -> List[Tuple[str, int, str]]:
        terms = self.extract_terms(query)
        if not terms:
            return []
        hits: List[Tuple[str, int, str]] = []
        seen = set()
        cap = limit or self.settings.code_search_limit
        for term in terms:
            results = self._run_rg(self.repo_root, term, "*.py")
            for rel_path, line_no, content in results:
                key = (rel_path, line_no)
                if key in seen:
                    continue
                seen.add(key)
                hits.append((rel_path, line_no, content.strip()))
                if len(hits) >= cap:
                    return hits
        return hits

    def search_notes(self, query: str, limit: int = 3) -> List[Tuple[str, int, str]]:
        terms = self.extract_terms(query)
        if not terms:
            return []
        hits: List[Tuple[str, int, str]] = []
        seen = set()
        for term in terms:
            results = self._run_rg(self.notes_root, term, "sglang-*.md")
            for rel_path, line_no, content in results:
                key = (rel_path, line_no)
                if key in seen:
                    continue
                seen.add(key)
                hits.append((rel_path, line_no, content.strip()))
                if len(hits) >= limit:
                    return hits
        return hits

    def build_context(self, question: str) -> str:
        repo_hits = self.search_repo(question)
        note_hits = self.search_notes(question)
        sections: List[str] = []

        if repo_hits:
            repo_lines = ["[Code Search Hits]"]
            for rel_path, line_no, _content in repo_hits[: self.settings.code_search_limit]:
                snippet = self.read_file_excerpt(rel_path, line_no)
                repo_lines.append("{0}:{1}\n{2}".format(rel_path, line_no, snippet))
            sections.append("\n\n".join(repo_lines))

        if note_hits:
            note_lines = ["[Local Study Notes]"]
            for rel_path, line_no, content in note_hits[:3]:
                note_lines.append("{0}:{1} {2}".format(rel_path, line_no, content))
            sections.append("\n".join(note_lines))

        return "\n\n".join(sections).strip()

    def read_file_excerpt(self, relative_path: str, line_no: int, context: Optional[int] = None) -> str:
        context_lines = context or self.settings.snippet_context_lines
        full_path = (self.repo_root / relative_path).resolve()
        if not full_path.exists():
            return "File not found: {0}".format(relative_path)

        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, line_no - context_lines - 1)
        end = min(len(lines), line_no + context_lines)
        rendered = []
        for idx in range(start, end):
            rendered.append("{0:>4}: {1}".format(idx + 1, lines[idx]))
        return "\n".join(rendered)

    def read_by_user_reference(self, reference: str) -> str:
        raw = reference.strip().replace("/", "\\")
        if ":" in raw:
            path_part, line_part = raw.rsplit(":", 1)
            try:
                line_no = int(line_part)
            except ValueError:
                path_part = raw
                line_no = 1
        else:
            path_part = raw
            line_no = 1
        return self.read_file_excerpt(path_part, line_no)

    @staticmethod
    def extract_terms(text: str) -> List[str]:
        code_spans = re.findall(r"`([^`]+)`", text)
        token_candidates = re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", text)
        terms: List[str] = []
        for token in code_spans + token_candidates:
            cleaned = token.strip(" ,.;:()[]{}<>\"'")
            if len(cleaned) < 3:
                continue
            if cleaned.lower() in COMMON_IDENTIFIERS:
                continue
            if cleaned not in terms:
                terms.append(cleaned)
        return terms[:6]

    @staticmethod
    def _run_rg(base_dir: Path, pattern: str, glob: str) -> List[Tuple[str, int, str]]:
        command = [
            "rg",
            "-n",
            "--no-heading",
            "--color",
            "never",
            "--glob",
            glob,
            pattern,
            ".",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except FileNotFoundError:
            return []

        if result.returncode not in (0, 1):
            return []

        stdout = result.stdout or ""
        matches: List[Tuple[str, int, str]] = []
        for line in stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) != 3:
                continue
            rel_path, line_no, content = parts
            try:
                matches.append((rel_path.lstrip(".\\"), int(line_no), content))
            except ValueError:
                continue
        return matches


class LocalCommandHandler:
    def __init__(self, db: BotDB, repo_tools: RepoTools) -> None:
        self.db = db
        self.repo_tools = repo_tools

    def maybe_handle(self, user_id: str, text: str) -> Optional[str]:
        stripped = text.strip()
        if not stripped:
            return "消息是空的，可以直接问源码问题，或者发 `/help` 看命令。"

        lowered = stripped.lower()

        if lowered == "/help":
            return (
                "可用命令：\n"
                "/task add <内容>\n"
                "/task list\n"
                "/task done <任务ID>\n"
                "/note <学习笔记>\n"
                "/code <关键词>\n"
                "/file <相对路径[:行号]>"
            )

        if lowered.startswith("/task add "):
            description = stripped[10:].strip()
            if not description:
                return "任务内容不能为空。"
            task_id = self.db.add_task(user_id, description)
            return "已添加任务 #{0}: {1}".format(task_id, description)

        if stripped.startswith("待办：") or stripped.startswith("加入待办：") or stripped.startswith("添加任务："):
            description = stripped.split("：", 1)[1].strip()
            if not description:
                return "任务内容不能为空。"
            task_id = self.db.add_task(user_id, description)
            return "已添加任务 #{0}: {1}".format(task_id, description)

        if lowered == "/task list" or re.search(r"(列出|看看|查看).*(任务|待办)", stripped):
            return self._format_tasks(user_id)

        if lowered.startswith("/task done "):
            number = stripped[11:].strip()
            if not number.isdigit():
                return "请用 `/task done 任务ID` 的格式。"
            success = self.db.complete_task(user_id, int(number))
            if success:
                return "任务 #{0} 已完成。".format(number)
            return "没有找到可完成的任务 #{0}。".format(number)

        if lowered.startswith("/note "):
            content = stripped[6:].strip()
            if not content:
                return "笔记内容不能为空。"
            note_id = self.db.add_note(user_id, content)
            return "已记录笔记 #{0}。".format(note_id)

        if stripped.startswith("笔记：") or stripped.startswith("记录笔记："):
            content = stripped.split("：", 1)[1].strip()
            if not content:
                return "笔记内容不能为空。"
            note_id = self.db.add_note(user_id, content)
            return "已记录笔记 #{0}。".format(note_id)

        if lowered.startswith("/code "):
            keyword = stripped[6:].strip()
            if not keyword:
                return "请给一个关键词，比如 `/code Scheduler`。"
            return self._format_code_hits(keyword)

        if lowered.startswith("/file "):
            reference = stripped[6:].strip()
            if not reference:
                return "请给一个路径，比如 `/file python/sglang/srt/managers/tokenizer_manager.py:1`。"
            return self.repo_tools.read_by_user_reference(reference)

        return None

    def _format_tasks(self, user_id: str) -> str:
        tasks = self.db.list_tasks(user_id)
        if not tasks:
            return "当前没有未完成任务。"
        lines = ["当前未完成任务："]
        for row in tasks:
            lines.append("#{0} {1}".format(row["id"], row["description"]))
        return "\n".join(lines)

    def _format_code_hits(self, keyword: str) -> str:
        hits = self.repo_tools.search_repo(keyword, limit=6)
        if not hits:
            return "没有搜到 `{0}` 的直接命中。".format(keyword)
        lines = ["代码搜索结果："]
        for rel_path, line_no, content in hits:
            lines.append("{0}:{1} {2}".format(rel_path, line_no, content))
        return "\n".join(lines)
