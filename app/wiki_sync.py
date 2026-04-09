import argparse
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs):
        return False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_WIKI_URL = os.getenv("FEISHU_WIKI_URL", "").strip()
DEFAULT_NOTE_DIR = Path(
    os.getenv("SGLANG_NOTES_DIR", str(PROJECT_ROOT / "notes"))
).resolve()
DEFAULT_STATE_FILE = Path(
    os.getenv(
        "SGLANG_LEARNING_STATE_FILE",
        str(DEFAULT_NOTE_DIR / "sglang-learning-state.md"),
    )
).resolve()
DEFAULT_REGISTRY = PROJECT_ROOT / "data" / "wiki_sync_registry.json"
DEFAULT_FEISHU_BASE_URL = "https://open.feishu.cn"
CC_CONNECT_CONFIG = Path.home() / ".cc-connect" / "config.toml"


class WikiSyncError(RuntimeError):
    pass


class SimpleFeishuClient:
    def __init__(self, app_id: str, app_secret: str, base_url: str = DEFAULT_FEISHU_BASE_URL) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._token: Optional[str] = None
        self._expire_at = 0.0

    def _tenant_access_token(self) -> str:
        if self._token and time.time() < self._expire_at:
            return self._token

        response = requests.post(
            self.base_url + "/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise WikiSyncError("Failed to get tenant_access_token: %s" % payload)
        self._token = str(payload["tenant_access_token"])
        self._expire_at = time.time() + max(int(payload.get("expire", 7200)) - 120, 60)
        return self._token

    def request(self, method: str, path: str, *, params=None, json_body=None) -> Dict[str, object]:
        response = requests.request(
            method,
            self.base_url + path,
            headers={"Authorization": "Bearer " + self._tenant_access_token()},
            params=params,
            json=json_body,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise WikiSyncError("%s %s failed: %s" % (method, path, payload))
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync local markdown notes into Feishu Wiki/Docx.")
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve", help="Resolve a wiki URL or node token.")
    resolve.add_argument("--wiki-url", default=DEFAULT_WIKI_URL)

    sync_file = sub.add_parser("sync-file", help="Sync one markdown file to a child page under a wiki node.")
    sync_file.add_argument("--wiki-url", default=DEFAULT_WIKI_URL)
    sync_file.add_argument("--file", required=True)
    sync_file.add_argument("--title")
    sync_file.add_argument("--force", action="store_true")

    sync_latest = sub.add_parser("sync-latest", help="Sync the latest note file and the learning state file.")
    sync_latest.add_argument("--wiki-url", default=DEFAULT_WIKI_URL)
    sync_latest.add_argument("--force", action="store_true")
    sync_latest.add_argument("--include-state", action="store_true", default=True)

    sync_all = sub.add_parser("sync-all", help="Sync all note files and the learning state file.")
    sync_all.add_argument("--wiki-url", default=DEFAULT_WIKI_URL)
    sync_all.add_argument("--force", action="store_true")
    sync_all.add_argument("--include-state", action="store_true", default=True)

    return parser.parse_args()


def load_registry(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(path: Path, registry: Dict[str, Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def markdown_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derive_title(path: Path) -> str:
    stem = path.stem.replace("-", " ").replace("_", " ").strip()
    if stem.lower() == "sglang-learning-state":
        return "SGLang 学习状态"
    return stem


def parse_cc_connect_credentials() -> Tuple[str, str]:
    if not CC_CONNECT_CONFIG.exists():
        return "", ""
    text = CC_CONNECT_CONFIG.read_text(encoding="utf-8", errors="replace")
    app_id_match = re.search(r'(?m)^\s*app_id\s*=\s*"([^"]+)"', text)
    secret_match = re.search(r'(?m)^\s*app_secret\s*=\s*"([^"]+)"', text)
    return (
        app_id_match.group(1).strip() if app_id_match else "",
        secret_match.group(1).strip() if secret_match else "",
    )


def build_client() -> SimpleFeishuClient:
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        app_id, app_secret = parse_cc_connect_credentials()
    if not app_id or not app_secret:
        raise WikiSyncError("Missing FEISHU_APP_ID / FEISHU_APP_SECRET.")
    return SimpleFeishuClient(app_id, app_secret)


def extract_wiki_token(wiki_url_or_token: str) -> str:
    raw = wiki_url_or_token.strip()
    match = re.search(r"/wiki/([A-Za-z0-9]+)", raw)
    if match:
        return match.group(1)
    if raw:
        return raw
    raise WikiSyncError("Wiki URL or node token is empty.")


def get_wiki_node(client: SimpleFeishuClient, node_token: str) -> Dict[str, object]:
    payload = client.request("GET", "/open-apis/wiki/v2/spaces/get_node", params={"token": node_token})
    node = payload.get("data", {}).get("node")
    if not isinstance(node, dict):
        raise WikiSyncError("Wiki node lookup returned no node: %s" % payload)
    return node


def create_wiki_child_page(
    client: SimpleFeishuClient,
    *,
    space_id: str,
    parent_node_token: str,
    title: str,
) -> Dict[str, object]:
    payload = client.request(
        "POST",
        "/open-apis/wiki/v2/spaces/{0}/nodes".format(space_id),
        json_body={
            "parent_node_token": parent_node_token,
            "obj_type": "docx",
            "title": title,
        },
    )
    data = payload.get("data", {})
    node = data.get("node")
    if isinstance(node, dict):
        return node
    if isinstance(data, dict):
        return data
    raise WikiSyncError("Create wiki child page returned unexpected payload: %s" % payload)


def document_children(client: SimpleFeishuClient, document_id: str, block_id: str) -> List[str]:
    page_token = ""
    children: List[str] = []
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        payload = client.request(
            "GET",
            "/open-apis/docx/v1/documents/{0}/blocks/{1}/children".format(document_id, block_id),
            params=params,
        )
        items = payload.get("data", {}).get("items", [])
        for item in items:
            if isinstance(item, dict) and item.get("block_id"):
                children.append(str(item["block_id"]))
        page_token = str(payload.get("data", {}).get("page_token", ""))
        if not bool(payload.get("data", {}).get("has_more")):
            break
    return children


def clear_document(client: SimpleFeishuClient, document_id: str) -> None:
    while True:
        children = document_children(client, document_id, document_id)
        if not children:
            return
        client.request(
            "DELETE",
            "/open-apis/docx/v1/documents/{0}/blocks/{1}/children/batch_delete".format(document_id, document_id),
            params={"client_token": str(uuid.uuid4())},
            json_body={"start_index": 0, "end_index": len(children)},
        )


def text_block(block_type: int, key: str, text: str) -> Dict[str, object]:
    return {
        "block_type": block_type,
        key: {
            "elements": [{"text_run": {"content": text, "text_element_style": {}}}],
            "style": {},
        },
    }


def render_markdown_blocks(markdown_text: str) -> List[Dict[str, object]]:
    blocks: List[Dict[str, object]] = []
    paragraph: List[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        content = " ".join(line.strip() for line in paragraph if line.strip())
        if content:
            blocks.append(text_block(2, "text", content))
        paragraph.clear()

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush_paragraph()
            continue
        if line.startswith("```"):
            flush_paragraph()
            blocks.append(text_block(2, "text", line))
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            flush_paragraph()
            level = min(len(heading.group(1)), 6)
            blocks.append(text_block(2 + level, "heading{0}".format(level), heading.group(2).strip()))
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if bullet:
            flush_paragraph()
            blocks.append(text_block(12, "bullet", bullet.group(1).strip()))
            continue
        paragraph.append(line)

    flush_paragraph()
    return blocks


def create_children(client: SimpleFeishuClient, document_id: str, children: Iterable[Dict[str, object]]) -> None:
    batch: List[Dict[str, object]] = []
    for child in children:
        batch.append(child)
        if len(batch) >= 50:
            _post_children(client, document_id, batch)
            batch = []
    if batch:
        _post_children(client, document_id, batch)


def _post_children(client: SimpleFeishuClient, document_id: str, batch: List[Dict[str, object]]) -> None:
    client.request(
        "POST",
        "/open-apis/docx/v1/documents/{0}/blocks/{1}/children".format(document_id, document_id),
        params={"client_token": str(uuid.uuid4())},
        json_body={"index": 0, "children": batch},
    )


def sync_one_file(
    client: SimpleFeishuClient,
    registry: Dict[str, Dict[str, str]],
    *,
    wiki_url: str,
    source_path: Path,
    title: Optional[str] = None,
    force: bool = False,
) -> Dict[str, str]:
    if not source_path.exists():
        raise WikiSyncError("Source file does not exist: {0}".format(source_path))

    source_key = str(source_path.resolve())
    source_hash = markdown_sha(source_path)
    if not force and source_key in registry and registry[source_key].get("source_hash") == source_hash:
        return registry[source_key]

    parent_token = extract_wiki_token(wiki_url)
    parent_node = get_wiki_node(client, parent_token)
    space_id = str(parent_node["space_id"])
    note_title = title or derive_title(source_path)

    entry = registry.get(source_key)
    if entry and entry.get("document_id"):
        document_id = entry["document_id"]
        node_token = entry.get("node_token", "")
    else:
        created = create_wiki_child_page(
            client,
            space_id=space_id,
            parent_node_token=parent_token,
            title=note_title,
        )
        document_id = str(created.get("obj_token", ""))
        node_token = str(created.get("node_token", ""))
        if not document_id:
            raise WikiSyncError("Created wiki page but did not get obj_token/document_id: %s" % created)

    clear_document(client, document_id)
    blocks = render_markdown_blocks(source_path.read_text(encoding="utf-8"))
    if not blocks:
        blocks = [text_block(2, "text", "(empty note)")]
    create_children(client, document_id, blocks)

    entry = {
        "title": note_title,
        "source_hash": source_hash,
        "node_token": node_token,
        "document_id": document_id,
        "wiki_parent_token": parent_token,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    registry[source_key] = entry
    return entry


def latest_note_file() -> Path:
    note_files = sorted(
        [path for path in DEFAULT_NOTE_DIR.glob("*.md") if path.is_file()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not note_files:
        raise WikiSyncError("No note files found in {0}".format(DEFAULT_NOTE_DIR))
    return note_files[0]


def print_json(data: Dict[str, object]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()
    if not args.wiki_url:
        raise WikiSyncError("Missing wiki url. Set FEISHU_WIKI_URL or pass --wiki-url.")
    client = build_client()
    registry = load_registry(DEFAULT_REGISTRY)

    if args.command == "resolve":
        node = get_wiki_node(client, extract_wiki_token(args.wiki_url))
        print_json(node)
        return

    if args.command == "sync-file":
        entry = sync_one_file(
            client,
            registry,
            wiki_url=args.wiki_url,
            source_path=Path(args.file),
            title=args.title,
            force=args.force,
        )
        save_registry(DEFAULT_REGISTRY, registry)
        print_json(entry)
        return

    if args.command == "sync-latest":
        latest = latest_note_file()
        results = {
            str(latest): sync_one_file(
                client,
                registry,
                wiki_url=args.wiki_url,
                source_path=latest,
                force=args.force,
            )
        }
        if args.include_state and DEFAULT_STATE_FILE.exists():
            results[str(DEFAULT_STATE_FILE)] = sync_one_file(
                client,
                registry,
                wiki_url=args.wiki_url,
                source_path=DEFAULT_STATE_FILE,
                title="SGLang 学习状态",
                force=args.force,
            )
        save_registry(DEFAULT_REGISTRY, registry)
        print_json(results)
        return

    if args.command == "sync-all":
        results: Dict[str, Dict[str, str]] = {}
        for path in sorted(DEFAULT_NOTE_DIR.glob("*.md")):
            results[str(path)] = sync_one_file(
                client,
                registry,
                wiki_url=args.wiki_url,
                source_path=path,
                force=args.force,
            )
        if args.include_state and DEFAULT_STATE_FILE.exists():
            results[str(DEFAULT_STATE_FILE)] = sync_one_file(
                client,
                registry,
                wiki_url=args.wiki_url,
                source_path=DEFAULT_STATE_FILE,
                title="SGLang 学习状态",
                force=args.force,
            )
        save_registry(DEFAULT_REGISTRY, registry)
        print_json(results)
        return

    raise WikiSyncError("Unknown command: %s" % args.command)


if __name__ == "__main__":
    main()
