# AI Infra Learning Assistant

一个面向源码学习场景的飞书助手模板，集成了：

- 飞书机器人收发消息
- OpenAI Responses API 对话生成
- 本地仓库代码检索与文件摘录
- SQLite 轻量任务与笔记管理
- 本地 Markdown 笔记同步到飞书知识库
- `cc-connect + Codex CLI` 的长连接工作流

这个项目最初用于 `sglang` 源码精读，但现在已经整理成可复用模板。你可以把它改造成任意本地仓库的学习助手、项目问答机器人或移动端源码伴读工具。

## 适合什么场景

- 在手机飞书里持续追问源码问题
- 对本地仓库做快速代码检索和上下文摘录
- 记录学习待办和阶段性笔记
- 把本地 Markdown 笔记同步到飞书知识库，方便跨设备复习

## 项目结构

```text
ai-infra-learning-assistant/
  app/
    main.py
    agent.py
    config.py
    db.py
    feishu.py
    openai_client.py
    tools.py
    wiki_sync.py
    wiki_sync.ps1
  data/
  docs/
    usage.zh-CN.md
    cc-connect-setup.zh-CN.md
    cc-connect.config.toml.example
  notes/
  .env.example
  .gitignore
  requirements.txt
```

## 两种运行方式

### 1. Webhook 模式

运行 FastAPI 服务，对接飞书事件订阅：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

适合你想自己掌控消息处理、笔记同步和本地工具逻辑时使用。

### 2. `cc-connect` 模式

如果你想直接把 Codex CLI 接到飞书，可以用 `cc-connect` 长连接模式。配置模板在 [cc-connect.config.toml.example](docs/cc-connect.config.toml.example)，说明在 [cc-connect-setup.zh-CN.md](docs/cc-connect-setup.zh-CN.md)。

这种模式更适合：

- 想直接把本地 Codex 工作区搬到飞书
- 需要 `/new`、`/switch` 这类会话控制
- 想结合本地 shell、repo、知识库同步工作流

## 快速开始

1. 复制 [.env.example](.env.example) 为 `.env`
2. 填好 OpenAI 和飞书应用凭证
3. 把 `SGLANG_REPO` 改成你的本地仓库路径
4. 按 [usage.zh-CN.md](docs/usage.zh-CN.md) 跑通 webhook 或 `cc-connect`

## 知识库同步

项目自带两个同步入口：

- Python 版：[wiki_sync.py](app/wiki_sync.py)
- PowerShell 版：[wiki_sync.ps1](app/wiki_sync.ps1)

常用命令：

```powershell
python app\wiki_sync.py resolve --wiki-url "https://your-domain.feishu.cn/wiki/xxxxx"
python app\wiki_sync.py sync-latest --wiki-url "https://your-domain.feishu.cn/wiki/xxxxx"
python app\wiki_sync.py sync-all --wiki-url "https://your-domain.feishu.cn/wiki/xxxxx"
```

## 开源说明

- 仓库默认不提交 `.env`、运行数据库、同步 registry 和私有笔记
- `notes/` 目录只保留空目录结构，方便你本地生成自己的学习笔记
- 如果你要公开部署，请务必自行检查飞书权限范围和密钥管理方式

## 文档

- 使用说明：[usage.zh-CN.md](docs/usage.zh-CN.md)
- `cc-connect` 配置指南：[cc-connect-setup.zh-CN.md](docs/cc-connect-setup.zh-CN.md)

## License

MIT
