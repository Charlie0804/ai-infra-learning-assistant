# 飞书 + cc-connect 配置清单（通用模板）

## 1. 适用场景

如果你想直接把本地 Codex CLI 工作区接到飞书，而不是自己跑 webhook 服务，这份模板更适合你。

典型用途：

- 在手机飞书里继续本地源码学习
- 用 `/new`、`/switch` 管理不同主题会话
- 让 Codex 在指定仓库目录里读代码、跑命令、生成笔记

## 2. 飞书后台配置顺序

1. 打开 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 开启机器人能力
4. 事件订阅选择长连接
5. 添加事件 `im.message.receive_v1`
6. 在权限管理里开通消息相关权限
7. 创建版本
8. 发布

## 3. 最小权限建议

私聊最小集合：

- `contact:user.base:readonly`
- `im:message.p2p_msg:readonly`
- `im:message:send_as_bot`

如果你还想在群聊里 `@机器人`：

- `im:message.group_at_msg:readonly`
- `im:message.group_msg`

如果后面要让机器人辅助知识库同步或文档写入，再额外开：

- `docx:document`
- `drive:drive`
- `wiki:wiki`

## 4. 需要准备的凭证

- `App ID`
- `App Secret`

把它们填入 `~/.cc-connect/config.toml`。

## 5. 推荐配置项

[cc-connect.config.toml.example](cc-connect.config.toml.example) 里保留了一份最小模板。

几个关键项的含义：

- `work_dir`
  Codex 实际工作的仓库目录。
- `mode = "yolo"`
  允许更积极地使用本地工具，适合源码阅读和自动化笔记。
- `quiet = true`
  减少飞书里的过程噪音。
- `progress_style = "compact"`
  更适合手机阅读。

## 6. 启动

Windows 示例：

```powershell
& "$env:APPDATA\npm\cc-connect.cmd" --config "$env:USERPROFILE\.cc-connect\config.toml"
```

## 7. 常用会话命令

- `/new <name>`
- `/list`
- `/switch <id>`
- `/current`
- `/history 20`
- `/mode yolo`
- `/reasoning high`
- `/quiet`
- `/help`

## 8. 推荐起手提示词

```text
请作为我的源码学习助手，在当前 work_dir 仓库中工作。
先用中文概览项目结构，再按我指定的主线继续精读。
回答时尽量给出文件路径、关键函数和调用关系。
```
