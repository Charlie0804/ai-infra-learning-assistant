# 使用说明

## 1. 准备条件

- 一个飞书企业自建应用
- OpenAI API Key 或可用的 Codex CLI 认证
- 一份本地源码仓库
- Windows 或 Linux 环境

## 2. 环境变量

复制仓库根目录下的 `.env.example` 为 `.env`，至少填这些值：

- `OPENAI_API_KEY`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_VERIFICATION_TOKEN`
- `SGLANG_REPO`

如果你要同步知识库，再补：

- `FEISHU_WIKI_URL`

如果你把笔记放在自定义目录，也可以补：

- `SGLANG_NOTES_ROOT`
- `SGLANG_NOTES_DIR`
- `SGLANG_LEARNING_STATE_FILE`

## 3. Webhook 模式

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

启动服务：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

飞书后台事件订阅地址：

```text
https://你的公网域名/webhook/feishu/events
```

## 4. `cc-connect` 模式

更适合源码学习型对话。基本步骤：

1. 安装 `cc-connect`
2. 复制 [cc-connect.config.toml.example](cc-connect.config.toml.example) 到 `~/.cc-connect/config.toml`
3. 填入你的飞书 `App ID` 和 `App Secret`
4. 把 `work_dir` 改成你的目标仓库
5. 启动 `cc-connect`

## 5. 本地命令能力

Webhook 版当前支持这些命令：

- `/help`
- `/task add <内容>`
- `/task list`
- `/task done <id>`
- `/note <内容>`
- `/code <关键词>`
- `/file <相对路径[:行号]>`

普通自然语言问题也可以直接发，比如：

- `Scheduler 主循环是怎么挑新 batch 的`
- `TokenizerManager.generate_request 的职责边界是什么`
- `帮我总结一下今天还没完成的阅读任务`

## 6. 知识库同步

同步最新笔记：

```powershell
python app\wiki_sync.py sync-latest --wiki-url "https://your-domain.feishu.cn/wiki/xxxxx"
```

全量同步：

```powershell
python app\wiki_sync.py sync-all --wiki-url "https://your-domain.feishu.cn/wiki/xxxxx"
```

PowerShell 版本：

```powershell
.\app\wiki_sync.ps1 -Command sync-latest -WikiUrl "https://your-domain.feishu.cn/wiki/xxxxx"
```

## 7. 推荐目录约定

如果你也想像源码学习助手那样沉淀本地笔记，推荐这样放：

```text
notes/
  sglang-learning-state.md
  scheduler-main-loop.md
  tokenizer-manager-generate-request.md
```

## 8. 适合继续扩展的方向

- 飞书事件加密支持
- OpenAI 托管会话状态
- 更强的代码调用链提取
- 自动摘要和阶段性学习报告
- 多仓库切换
