# 试卷第4题提交审查

选题：短视频脚本 Agent。只验收第4题，不包含第1–3题的业务功能。

下表记录2026-10-29首次提交审查。2026-10-30本地新增聊天入口 run_chat.py，当前全套67项测试通过，离线对话6/6通过；本次同步新增部分，真实聊天系统效果评测尚未完成，见 [评估更新](03-evaluation.md) 和 [聊天说明](07-chat-guide.md)。

| 试卷要求 | 对应实现与材料 | 审查结果 |
|---|---|---|
| 用户、目标、范围和成功标准 | docs/01-requirements.md | 已具备 |
| CLI、HTTP、Notebook三选一 | run.py + README/PyCharm说明；CLI入口 | 已具备 |
| 主题、受众、平台、时长、风格 | data/request.json、schemas.py | 已具备 |
| 素材与品牌规则 | data/materials.json、brand_rules.json | 已具备，明确标为合成 |
| 检索、时长估算、规则检查 | tools.py | 已具备 |
| 标题、分镜、旁白/字幕、总时长、素材ID、风险、状态 | output.json、script.md、checks与sources | 已具备 |
| 模型选动作→工具→观察→再决策 | agent.py + model_client.py，最终真实Trace | 已具备；不是Mock路径冒充 |
| 至少两条不同路径 | final-real/C05-overlong 与 C08-empty-rewrite，另有C06/C07 | 已具备 |
| 步数/调用上限与明确未完成 | 12步、24次模型调用；step_limit/model_call_limit | 已具备 |
| 正常生成 | final-real/C01-normal，历史入口修复版本另有user-real | 已具备 |
| 缺关键信息 | final-real/C02-missing | 已具备 |
| 无素材 | final-real/C03-no-material | 已具备 |
| 工具失败 | final-real/C04-tool-failure、C07-recover-failure | 已具备，故障注入有记录 |
| 超时长修正或明确失败 | C05：21.15→10.10秒；H03：明确未完成 | 已具备；初稿夹具来源已披露 |
| 至少3组输入/实际输出/Trace | examples/final-real全11组，以及user-real | 已具备 |
| 可执行工程测试 | tests/，40项 | 已具备 |
| README、src/tests/examples/data、五份指定docs | 项目根目录与docs | 已具备 |
| 依赖文件和.env.example | pyproject.toml（运行依赖为空）、.env.example | 已具备 |
| 框架职责与版本 | Python标准库，无第三方Agent框架；run.json记Python版本 | 已具备 |
| AI使用、个人修改与验证 | docs/04-ai-usage.md，记录用户实际PyCharm运行 | 已补充，不虚构个人编程贡献 |
| 实际用时与未完成部分 | docs/03-evaluation.md | API运行耗时已记录；净人工投入未连续计时，未宣称3小时内完成 |
| 题号、GitHub URL、最终commit SHA | submission-info.json提供题号与URL，最终交付消息提供完整commit SHA | 上传后回读核验 |
| 不提交真实密钥与隐私数据 | 排除.env、runs、.idea、.codex；提交清单密钥扫描 | 上传前执行 |

## 审查结论与限制

核心实现、五类验收与动态路径有实际证据，材料可用于第4题提交；这不等于官方评分或生产可用性认证。语义审核与决策使用同一模型，已发现易用性/兼容性推断漏判；保守词表也可能误伤创作画面。独立人工质量评分、外部盲测与稳定性重复评测未完成，必须保留在报告中。

界面、线上部署、多Agent、视频渲染不是必需；没有这些功能不是遗漏。未添加虚构性能数字、人工评分或工作用时。
