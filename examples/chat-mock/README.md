# 离线多轮对话实际记录

2026-10-30执行 `scripts/evaluate_chat.py --output examples/chat-mock` 生成，6/6符合预期。每个随机会话目录包含原始 state.json 与逐轮文件；summary.json 的 record 指向对应轮次。

没有执行Agent的纯追问轮次只有 dialogue.json；执行Agent的轮次包含完整输入、素材、规则、实际结果、Trace与稿件历史。生成轮次已通过独立记录审计。

这是固定规则离线模拟，不证明真实模型决策与创作效果。15秒限制案例得到3.65秒，明显偏短；风格修改返回未完成。原始记录保留这些边界。

重新验收请使用新的输出目录，例如：`python scripts/evaluate_chat.py --output runs/chat-eval-new`。
