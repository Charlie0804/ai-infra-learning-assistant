# AI Infra Learning Assistant

一个面向“本地代码仓库学习 + 飞书移动端对话 + 本地笔记沉淀 + 飞书知识库同步”的开源模板。

它适合把本地仓库接到飞书里，让机器人像源码学习助手一样工作：
- 在手机飞书里追问源码问题
- 调用本地仓库检索和文件摘录能力
- 先落本地 Markdown 笔记，再同步到飞书知识库
- 用 `cc-connect + Codex CLI` 直接把本地工作区搬到飞书
- 或者用 Webhook 方式自行控制消息处理逻辑

这个项目最初来自 `sglang` 源码精读场景，后来整理成通用模板，方便迁移到其他本地仓库。

## 适合什么场景

- 源码学习助手
- 移动端项目问答机器人
- 本地仓库的任务/笔记沉淀工具
- 飞书知识库同步助手
- `cc-connect` 长连接工作流模板

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
  docs/
    usage.zh-CN.md
    cc-connect-setup.zh-CN.md
    cc-connect.config.toml.example
  scripts/
    cc-connect/
      start-with-proxy.ps1
      restart-with-proxy.ps1
      check-health.ps1
      repair-if-unhealthy.ps1
  data/
  notes/
  .env.example
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

适合你想完全掌控消息处理、工具调用、笔记逻辑和知识库同步流程时使用。

### 2. `cc-connect` 模式

如果你想直接把本地 `Codex CLI` 工作区接到飞书，推荐用 `cc-connect` 长连接模式。

这个模式更适合：
- 手机上的连续源码学习对话
- `/new`、`/switch` 这类会话管理
- 依赖本地 shell / repo / 笔记文件的工作流

模板配置见：
- [docs/cc-connect.config.toml.example](docs/cc-connect.config.toml.example)
- [docs/cc-connect-setup.zh-CN.md](docs/cc-connect-setup.zh-CN.md)

## 源码教师模式

这一套模板很适合做“轻约束源码教师”：
- 主教学方法交给技能或模型本身
- 本地状态文件只记录“当前主题 / 已掌握主题 / 当前误区 / 下一候选主题”
- 笔记优先落到本地，再异步同步知识库
- 不因为“已经有笔记”就自动推进主题

推荐的分工是：
- `skill`：负责怎么读源码、怎么解释、怎么追问
- `state`：负责教到哪、哪里没收口
- `style`：只做轻量护栏，不写死模型措辞

## 代理环境与稳定性

如果你的机器访问飞书或 OpenAI 依赖本地代理，仓库里已经附带一套 `cc-connect` 启动与健康检查脚本：

- [scripts/cc-connect/start-with-proxy.ps1](scripts/cc-connect/start-with-proxy.ps1)
- [scripts/cc-connect/restart-with-proxy.ps1](scripts/cc-connect/restart-with-proxy.ps1)
- [scripts/cc-connect/check-health.ps1](scripts/cc-connect/check-health.ps1)
- [scripts/cc-connect/repair-if-unhealthy.ps1](scripts/cc-connect/repair-if-unhealthy.ps1)

这套脚本适合解决：
- 需要显式注入 `HTTP_PROXY` / `HTTPS_PROXY`
- 飞书长连接偶发断线
- `cc-connect` 在线但消息体验不稳定

## 快速开始

1. 复制 `.env.example` 为 `.env`
2. 填好 OpenAI 和飞书应用凭证
3. 把仓库路径配置成你的本地代码目录
4. 选择运行 Webhook 模式或 `cc-connect` 模式
5. 如需知识库同步，补上飞书 wiki / docx 相关权限

详细说明见：
- [docs/usage.zh-CN.md](docs/usage.zh-CN.md)
- [docs/cc-connect-setup.zh-CN.md](docs/cc-connect-setup.zh-CN.md)

## 知识库同步

项目自带两个同步入口：
- Python 版：[app/wiki_sync.py](app/wiki_sync.py)
- PowerShell 版：[app/wiki_sync.ps1](app/wiki_sync.ps1)

常用命令：

```powershell
python app\wiki_sync.py resolve --wiki-url "https://your-domain.feishu.cn/wiki/xxxxx"
python app\wiki_sync.py sync-latest --wiki-url "https://your-domain.feishu.cn/wiki/xxxxx"
python app\wiki_sync.py sync-all --wiki-url "https://your-domain.feishu.cn/wiki/xxxxx"
```

## 开源说明

- 仓库默认不提交 `.env`、本地数据库、同步 registry 和私有笔记内容
- `notes/` 目录仅保留空目录结构
- 各类路径、机器人凭证、知识库地址都需要你按自己的环境配置

## License

MIT
