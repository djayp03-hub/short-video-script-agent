# 本地多轮脚本对话 Implementation Plan

> For agentic workers: use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 PyCharm 运行 `run_chat.py` 后，通过本地浏览器连续补充需求、修改脚本、查看检查结果。

**Architecture:** Python 标准库 HTTP 服务提供静态页面与会话接口。对话规划器将自然语言和历史需求转换为严格结构化需求，生成任务继续调用现有 execute_run/Agent/ToolBox。每轮单独落盘，修改后的脚本重新检索与检查。

**Tech Stack:** Python 3.10+ 标准库，原生 HTML/CSS/JavaScript，无第三方运行依赖。

**执行结果：** 已完成本地实现、67项工程测试、6/6离线对话验收、原CLI的11/11离线回归与审计、Chrome浏览器检查及只读代码审查。开发验证时未调用真实聊天服务，新聊天系统效果未评测。随后按用户要求同步GitHub和演示材料。记录见docs/03-evaluation.md新增章节。

**Spec:** 用户已同意本地浏览器聊天、会话记忆与追问续接；保留原 CLI。以下实现细节由助手选择。

## Global Constraints

- 仅绑定 127.0.0.1，默认端口 8765；端口占用时明确提示。
- mock/real 清晰区分，真实失败不自动切换 Mock。密钥只从本地环境读取。
- 每轮沿用 12 步、240 秒和 24 次 Agent API 上限，真实对话整理最多再调用 1 次模型。
- 会话最多 40 条用户消息，每条最多 4000 字；素材最多 20 条，每条正文最多 8000 字。
- 新需求缺项时追问；更换产品不复用上一产品稿件。相同产品改稿可带入旧稿，但清空检查并重新验证。
- 每轮输出和完整聊天状态存放 runs/chat/；旧验收与 PPT 保持历史版本的含义，不冒充新版本验证。

## Review Focus

- 追问回复后需求仍缺字段：不能随意填默认值后生成。
- 修改目标时长：不得复用旧检查；必须生成新运行记录。
- API 或配置失败：保留会话、错误状态和调用证据，不伪装成功。
- 不同会话与产品：资料、稿件与对话历史隔离。
- 本机网页输入与请求：按文本显示，校验 Host/Origin/随机请求令牌，限制请求体。

## Task 1：会话与模型对话层

- [x] 新增 tests/test_chat.py，先运行并确认功能缺失，再实现 chat.py。
- [x] ChatService.create_session(mode)、get_session(id)、send(id,message,attachments) 提供可持久化会话与逐轮产物。
- [x] LiveChatRouter 复用 LiveModel.complete；OfflineChatRouter 仅支持明确的示例表达并说明限制。
- [x] execute_run 增加 initial_draft_kind 元数据，区分测试夹具与对话旧稿。
- [x] 测试补参、追问续接、时长修正、新产品、资料附件、持久化、失败和非法模型结构。

## Task 2：本地服务与页面

- [x] 新增 tests/test_chat_http.py，先验证接口缺失，再实现 chat_server.py 与 run_chat.py。
- [x] 页面支持模式选择、新会话、需求摘要、素材补充、脚本/来源/风险/Trace、下载 Markdown/JSON。
- [x] 测试非法请求、来源、过大请求、会话隔离、服务关闭；浏览器实际操作验证正常交互与刷新。

## Task 3：交付与验证

- [x] 全套 unittest、离线会话实跑、产物审计、浏览器检查。
- [x] README、运行说明书、方案、AI 使用和评估文档追加本次功能及实际结果。
- [x] 明确真实对话是否实测；缺密钥时仅报告离线结果和失败，不虚报真实通过。
- [x] 当前任务先交付本地版本，不自动替换 GitHub 已提交考试版本。
