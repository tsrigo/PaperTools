# PaperTools 稳定性检查摘要

检查对象：`https://github.com/tsrigo/PaperTools` master 分支。

关键证据：仓库 README 说明流水线为“爬取 arXiv → LLM 筛选 → LLM 聚类 → 摘要/总结生成 → 网页生成”；`daily_update.sh` 当前只做一次流水线运行，成功后提交，失败后跳过；`.env.example` 仍包含 ModelScope/Prism/SJTU 混合 summary 默认项；`config.py` 中旧的 `_normalize_model_alias` 会把 MiniMax/DeepSeek reasoning 映射到其他模型。

本热修优先解决：

- SJTU model_id 精确映射，不再静默降级。
- summary 默认回到 SJTU，避免无 ModelScope/Prism key 时跑错 provider。
- 统一 OpenAI-compatible timeout/retry/proxy 行为。
- retry helper 增加 408/409/504/529 等状态码、OpenAI typed exceptions 和 jitter。
- 新增预检脚本，在真正消耗 API 前发现缺 key、模型 ID 拼错、依赖缺失。
- 新增 robust daily runner，支持锁、状态文件、滚动窗口、瞬时错误重试、永久错误快速失败、可选自动提交/推送。

注意：热修包不会包含或写入真实 API key。
