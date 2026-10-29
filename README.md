# 短视频脚本 Agent 

根据素材生成可编辑分镜，利用真实工具结果调整查询或脚本，并在当前版本通过时长、引用与品牌规则检查后结束。提供零第三方运行依赖的 Python CLI，以及明确标记的离线模拟入口。

本机另有可选 Codex Actions 配置，便于一键运行；包含个人解释器路径的 `.codex/` 不纳入仓库。评审可直接使用下方跨环境 CLI，或按运行说明书配置 PyCharm。真实生成需先填写自己的 `.env` 密钥。

第一次使用请阅读 [运行说明书](docs/运行说明书.md)，其中包含 Codex 按钮使用方式、PyCharm 配置，以及每个目录和文件的用途。下面的命令行示例是可选的另一种入口。

## 快速运行

在 PyCharm 中直接运行根目录 `run.py` 即可：不填参数时默认离线演示，自动从项目 `data/` 读取样例，并在项目 `runs/` 创建唯一的新目录。默认资料路径不受 IDE 工作目录影响。真实模型仍需显式选择 `--mode real`。

环境：Python 3.10+，在本项目根目录执行。验证所用 Python 版本及运行元数据保存在各示例的 `run.json`。

```bash
# 不安装任何依赖即可运行源码入口
python run.py --mode mock --output runs/offline-01

# 工程测试：不访问网络
python -m unittest discover -s tests -v

# 离线场景验收
python scripts/evaluate.py --mode mock --output runs/mock-suite-01
```

所有输出目录必须是新目录，已有记录不会覆盖。`run.py` 退出码：0 完成；2 合法的未完成/追问/失败状态；1 命令或文件错误。评测脚本按预期状态验收，正常追问和正确停止也可以通过用例。

可选安装：`python -m pip install -e .`，之后可用 `video-agent` 或 `python -m video_agent`。安装需要 setuptools；源码入口与 unittest 不需要安装依赖。

## 真实模型

复制 `.env.example` 为 `.env`，填写自己的 `VIDEO_API_KEY`。兼容现有 `DASHSCOPE_API_KEY`；显式传入的环境文件只读取，不复制到产物。实际模型由 `VIDEO_MODEL` 控制，默认 `qwen-plus`，服务地址可配置。

```bash
python run.py --mode real --env-file .env --output runs/live-01
python scripts/evaluate.py --mode real --env-file .env --output runs/real-suite-01
```

真实模式会发送输入和选定素材到配置的模型服务并产生调用费用。没有密钥或服务报错时返回明确失败，不自动替换为 Mock。所有自带素材均为合成资料。

## 输入与输出

默认输入在 `data/request.json`。必须提供 `theme/audience/platform/target_seconds/style`；`product` 可用于限定产品，`instructions` 可声明额外内容要求。

```bash
python run.py --input data/request.json --mode mock --max-steps 12 --output runs/custom-01
```

每次运行保存：

- `input.json/materials.json/rules.json`：确切输入与证据快照。
- `output.json/script.md`：结构化结果和可编辑脚本；未完成时保留草稿。
- `trace.jsonl`：模型动作、参数、简要依据、实际工具观察和修订号。
- `revisions.json`：草稿历史；`model-calls.json`：模型调用标识、结构化返回、耗时及实际用量。
- `run.json`：模式、模型、源代码哈希、数据哈希、故障配置、运行时间。

`completed` 表示当前版本通过自动检查；`needs_input` 表示需要补充；`incomplete` 表示约束无法满足或预算用尽；`failed` 表示输入/模型等错误。`human_review=pending` 始终提醒自动审核不等于独立人工核验。

时长由确定性公式计算，旁白与字幕并行取较长轨道，加上转场；不是已录制配音的实测长度。模型不能自行写一个“28 秒”绕过工具。

## 评审入口

1. [需求与验收](docs/01-requirements.md)
2. [方案与决策循环](docs/02-solution.md)
3. [实际验证结果及限制](docs/03-evaluation.md)
4. [AI 使用与贡献边界](docs/04-ai-usage.md)
5. [复盘](docs/05-retrospective.md)

最终验证目录为 `examples/final-real`、`examples/final-mock` 和 `examples/fresh-real`。代表性开发失败记录汇总在 `examples/development-failures.json`，过期中间目录已清理。当前40项工程测试通过、真实11/11自动合同验收通过；内容人工评分仍待完成，详见评测文档。

核验已保存记录与打分：

```bash
python scripts/verify_artifacts.py examples/final-real
python scripts/score_reviews.py examples/review-template.json --output runs-review-score.json
```

记录核验独立重算时长、校对引用、脚本哈希和实际检查事件。评分模板中的空分数不会被当成零或自动补满；填写具名评审、0–4 档评分和证据说明后才计算加权分。关键事实缺陷直接判为不合格，不能被其他分数抵消。自评量表不是官方分项标准。

## 故障与修正复现

`--faults path.json` 可注入 `{"search_materials":"once"}`、`"always"`、`"empty_once"` 或 `"empty_always"`。时长与规则工具也支持 once/always 故障；注入超时是模拟返回，不是真实网络超时。

`--initial-draft path.json` 可加载明确标记的初稿夹具，验证模型如何观察超限或违规并修改。评测脚本的 C05/C06 使用这种夹具，不声称是模型自然生成的错误初稿。评测清单保存完整夹具，可单独复跑。

## 范围与限制

离线 Mock 只检查程序机制，决策是固定规则、内容主要拼接原文，不代表生成效果。真实模式使用模型做事实语义审核，该审核与决策使用同一提供方，不是独立评审，可能共同出错。合成留出集也由同一开发助手设计，不属于外部盲测。

本次选题为 **第4题：短视频脚本 Agent**，提交仓库：https://github.com/djayp03-hub/short-video-script-agent 。最终 commit SHA 以提交时提供的完整哈希为准，也可在克隆后用 `git rev-parse HEAD` 查询。首版无业务 UI、数据库或多 Agent；已有结果不能直接推导真实业务的稳定准确率。


完整的逐项交付核对见 [试卷提交检查表](docs/06-submission-checklist.md)。本次提交前再次完成40项工程测试；最新真实记录见 `examples/user-real/`。规则结构校验修复后的本次模型启动检查见 `examples/submission-real/`，因本地缺少密钥明确返回 failed，未伪造为通过。
