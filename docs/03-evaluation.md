# 实际验证结果与限制

## 2026-10-30 本地多轮聊天扩展

当前全套67项测试通过，完整输出见 [chat-test-results.txt](../examples/chat-test-results.txt)。包含原CLI回归、新增会话/HTTP测试，以及改稿门禁、无效初稿校验、中断恢复、普通交流不强制补齐生成需求等回归。测试不调用真实服务。

原CLI另完成11/11离线场景回归与11/11产物审计，本地完整产物保存在 runs/chat-cli-regression，可用 `python scripts/evaluate.py --mode mock --output runs/cli-new` 重新生成。它仍只证明离线机制，不证明真实模型效果。

使用 `python scripts/evaluate_chat.py --output runs/chat-eval-new` 可复现离线多轮验收。本次 [6/6 场景通过](../examples/chat-mock/summary.json)：缺项追问、回复后生成、缩短后复检、离线风格改写明确未完成、无素材追问、补充素材后续跑。生成轮次同时使用 verify_artifacts.verify 独立复算时长和核对证据。

默认离线样例从24.40秒压缩为3.65秒，符合15秒上限，但明显偏短。这是固定模拟器取原文首句的结果，不能作为真实创作质量证明。

通过本机Chrome的独立无界面浏览器执行了补参、生成、缩短、不能改风格时的未完成、刷新恢复、素材补充续跑、Markdown下载、用户文本不执行为HTML、模式切换失败保留原会话、移动宽度布局检查。见 [浏览器检查记录](../examples/chat-browser-checks.json) 和 [实际页面截图](../examples/chat-ui.png)。没有页面JavaScript异常；截图来自离线模式。

真实模式启动记录见 [dialogue.json](../examples/chat-real-unavailable/turn-0001/dialogue.json)，明确 failed/missing_api_key、0次需求整理模型调用、未进入Agent执行，没有切换Mock。**新聊天入口的真实模型对话、自由改写和稳定性尚未验证**；下面保存的真实CLI案例属于历史代码版本，不冒充本次结果。

同产品、同主题带入旧稿时，本次新增 revision_required 门禁：未提交有变化的新稿不能完成。内容哈希变化仅证明稿件有变化，仍需模型与人工判断修改是否满足用户语义要求。真实语义审核漏判、合成数据独立性和真人配音校准的限制继续存在。

独立上下文的只读AI审查复核了会话、HTTP和最后增量，并独立运行66项测试；这仍不等于人类内容评分。审查发现非ASCII令牌造成500错误，已用回归修为403；另补充中途停止后恢复为明确未完成的测试。

本次按用户要求同步聊天代码、文档、验证材料与39页交互功能版PPT。首次提交的 cf74a4bf8cc210dc51ab9af3681a2b628baf279c 及旧 delivery-manifest.json 作为历史记录保留；本次完整 SHA 以 GitHub 最新提交及交付消息为准，避免在提交内容中循环填写自身哈希。开发期缺密钥记录不代表当前配置状态；当前本地已配置密钥，但尚未完成真实多轮系统效果评测。

## 2026-10-29 CLI 提交记录存档

启动路径修复更新：当前工程测试增加到 38 项，验证从 docs 工作目录启动绝对路径入口、无参数运行和连续运行输出不冲突。默认数据改为相对项目根目录定位；显式传入的相对路径仍相对当前工作目录。下文真实模型场景是先前版本保存的记录，本次入口修复未重新调用模型，不将其冒充为新版本真实评测。

验证日期：2026-10-29。本地实现与验证材料已交付，提交仓库为 https://github.com/djayp03-hub/short-video-script-agent 。以下都是实际运行结果；人工内容评分未完成，不给出综合效果分数。

## 结果

- 当前工程测试：40 项通过，见 [完整日志](../examples/test-results.txt)。初版36项，启动路径修复新增2项，提交审查的规则格式回归新增2项；命令：`python -m unittest discover -s tests -v`。
- 最终离线场景：11/11 自动合同验收通过，见 [汇总](../examples/final-mock/summary.json)。Mock 是固定规则模拟器，只证明流程机制。
- 最终真实场景：11/11 自动合同验收通过，实际使用 qwen-plus，见 [汇总](../examples/final-real/summary.json)。这是状态与约束验收，不是独立事实准确率。
- 新产品补充：代码冻结后对“便签打印机学习版”运行一次，返回 completed；见 [输出](../examples/fresh-real/output.json) 和 [Trace](../examples/fresh-real/trace.jsonl)。仍是同一助手设计的合成资料，不是外部盲测。
- 产物审计：最终真实 11/11、离线 11/11、新产品 1/1，通过来源、模型动作一致性、时长复算、修订与检查哈希核对，见各目录 artifact-audit.json。

| 场景 | 实际状态 | 自动验收 | 预计秒数 | 决策步数 |
|---|---|---|---:|---:|
| C01-normal | completed | 通过 | 12.6 | 8 |
| C02-missing | needs_input | 通过 | — | 0 |
| C03-no-material | needs_input | 通过 | — | 2 |
| C04-tool-failure | needs_input | 通过 | — | 8 |
| C05-overlong | completed | 通过 | 10.1 | 7 |
| C06-rule-risk | completed | 通过 | 12.35 | 7 |
| C07-recover-failure | completed | 通过 | 13.5 | 9 |
| C08-empty-rewrite | completed | 通过 | 13.5 | 9 |
| H01-new-product | completed | 通过 | 15.3 | 9 |
| H02-paraphrase | completed | 通过 | 21.15 | 5 |
| H03-impossible | incomplete | 通过 | 9.6 | 12 |

needs_input 和 incomplete 在资料不足、工具持续失败和不可行约束场景是正确终止。不能用 completed 的数量直接计算总体好坏。

## 可追踪的动态路径

1. [超时长修正](../examples/final-real/C05-overlong/trace.jsonl)：已提供初稿夹具，模型先检索并选择估时，真实结果 21.15 秒；再提交精简版本，真实结果 10.10 秒，规则检查通过后结束。第 3 步重复估时被运行时拒绝，仍保留在 Trace。初稿不是声称由模型自然生成。
2. [空结果后改写查询](../examples/final-real/C08-empty-rewrite/trace.jsonl)：第一次“剪映盒演示版 手动字幕 视频裁剪”被注入空结果，模型随后改为“剪映盒演示版 手动字幕”，再检索和生成。故障注入已在 run.json 标明。
3. [规则反馈修正](../examples/final-real/C06-rule-risk/trace.jsonl)：初稿夹具含“效率提升80%”“保证爆款”，实际工具拒绝，模型重写后重新估时和查规则。
4. [短暂失败恢复](../examples/final-real/C07-recover-failure/trace.jsonl)：首次检索注入超时后，模型选择后续动作并完成。

每组目录均含输入、实际输出、原始模型结构化返回、工具观察、素材和规则快照、草稿历史及运行元数据。script.md 是可编辑阅读版。

## 数据独立性与评分

## 最新版本的用户实际验证

用户在 PyCharm 使用既有 atguigu_ai 解释器执行根目录 run.py，参数为 `--mode real --env-file .env`。本次 [输入](../examples/user-real/input.json)、[输出](../examples/user-real/output.json)、[Trace](../examples/user-real/trace.jsonl) 和 [调用记录](../examples/user-real/model-calls.json) 已从 runs 原样复制到 examples/user-real。

结果：completed，8次决策加1次语义审核，9次API调用，总耗时47.109秒，模型等待47.093秒；生成脚本预计18.85秒。该次 source_hash 对应启动修复后的代码，补上了前述历史场景与当前入口版本之间的证据。

该记录只证明当前版本实际完成链路及自动检查。审查注意到标题“学生也能上手”含素材未提供的易用性判断；自动审核未拦截。这与 H01 文件兼容性问题一样，属于已知事实边界，不能把 completed 说成每条内容已独立核实。原始产物不做事后润色，保留给评审核查。

### 数据独立性说明

H01/H02/H03 原名带 heldout，但已被用于分析失败并调试，最终应算开发回归。历史 case-manifest/summary 保留原标签以保存运行原貌；本报告不把该标签当作独立性证明。新增 fresh 数据只在源代码冻结后验证一次，样本量很小。

[评分模板](../examples/review-template.json) 使用事实30、动态决策25、状态20、约束15、可用性10的项目自评权重，非官方细分评分。每维0–4档，需要填写评审身份与证据。关键缺陷直接判不合格；缺评分时保持 null，不能算一个完整总分。

命令：`python scripts/score_reviews.py examples/review-template.json --output runs-review-score.json`。当前 [评分输出](../examples/review-scores.json) 的 mean_score 为 null，全部待人工评分。

真实决策和语义审核使用同一模型，可能共同漏判。开发期间自动审核曾漏过无依据按钮位置，原始记录已汇入 [开发失败记录](../examples/development-failures.json)；后来补充 R04，但词表仍不全面。主助手抽查了最终正常、修正、规则风险、新产品的内容；这不等于独立人类评审。H01 中“导入剪辑软件”涉及素材未给出的文件兼容性，建议人工复核并避免把它当作已验证能力。

## 调用、时间与失败记录

最终11组累计实际 API 调用 87 次（含语义审核），各调用的 token 用量、服务返回模型标识和耗时在 model-calls.json。没有计算货币成本，因为未核对账户计费规则。

最终场景累计运行耗时 266.24 秒。开发过程中有多次中断，未连续记录人工专注工时，不能声称总开发时间在3小时内；计划的180分钟是预算而非实际工时。最早探索记录和最终运行的 UTC 时间均保留在 run.json。

目录清理时移除了重复的开发轮次和中止目录，保留两项代表性原始失败运行于 development-failures.json。最终版本全量结果及失败状态均保留；最新结论仅使用 final-real、final-mock、fresh-real。

## 复现命令与当前边界

```bash
python run.py --mode mock --output runs/offline-new
python scripts/evaluate.py --mode real --env-file .env --output runs/real-new
python scripts/verify_artifacts.py examples/final-real
python run.py --mode real --env-file .env --input data/fresh_request.json --materials data/fresh_materials.json --output runs/fresh-new
```

模型输出有随机性，重新运行可能不同；本轮没有做足够重复试验来证明稳定性。目标时长按上限验收，部分脚本明显短于30秒；文字卡片占比较高，平台风格适配与创作表现还需人工评价。估时是公式而非实录配音。外部隐藏评测、具名人工评分、视频制作和线上部署尚未进行。GitHub提交以最终交付的commit SHA为准。

## 提交前规则格式修复

审查发现规则误填为对象或字符串列表时可绕过规则循环或抛出AttributeError。新增规则数组、对象、字段及ID重复检查，错误时以ContractError明确失败并落盘完整终止材料；2项新增测试先复现失败后通过，全套40项通过。该修复改变了代码哈希，因此上述真实记录属于修复前版本。

发布前尝试当前版本真实启动，见 [submission-real/output.json](../examples/submission-real/output.json)，结果为failed/missing_api_key，模型调用次数0。本次可用本地配置没有模型密钥，未伪造当前版本的真实通过记录。规则校验修复未改变正常样例的模型协议或决策循环，但不等同于已重新验证真实模型效果。
