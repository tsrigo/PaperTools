# 2026-05-26 Paper Filter Manual Review

## Summary

- Source papers: 829
- Keyword excluded: 445
- Topic excluded: 262
- Prestige excluded: 61
- Published before review: 61
- Manual review result after policy correction: 39 KEEP, 11 BORDERLINE, 11 DROP
- Published after correction: 50

Root cause: the date did not fail the prestige gate. All 61 published papers had whitelist prestige evidence. The over-inclusion came from the topic stage: 56 of 61 were accepted by the LLM topic judge, which was too permissive around generic LLM RL/training/evaluation, Graph-RAG, non-LLM MARL, and domain applications that merely used agent frameworks.

Policy correction: generic LLM training/RLVR work such as GRPO/DAPO-style optimization remains in scope. DROP papers were removed from the 2026-05-26 published page. BORDERLINE papers remain published because they have plausible agent-system value but should be watched when tightening future policy.

## Paper-Level Review

| # | arXiv ID | Verdict | Action | Reason |
|---:|---|---|---|---|
| 1 | 2605.25981 | KEEP | Keep | CoT/ReAct agent trace-level robustness and failure analysis. |
| 2 | 2605.25971 | KEEP | Keep | Proactive agent architecture with memory and idle-time preparation. |
| 3 | 2605.25480 | KEEP | Keep | Agent-native retrieval with self-evolving correction for tool-using agents. |
| 4 | 2605.25379 | DROP | Removed | Graph-RAG / retrieval-state management is the core contribution. |
| 5 | 2605.25297 | BORDERLINE | Keep | Self-evolving code/feature generation, but applied AutoFE/cloud forecasting. |
| 6 | 2605.24432 | KEEP | Keep | LLMs improving LLMs for multi-turn interaction ability. |
| 7 | 2605.24266 | KEEP | Keep | Interactive deep research agent control and user steering. |
| 8 | 2605.24218 | KEEP | Keep | Training long-horizon deep research agents. |
| 9 | 2605.24517 | KEEP | Keep | Terminal agents learn world models from environment feedback. |
| 10 | 2605.24528 | BORDERLINE | Keep | LLM agents in cognitive induction experiment; agent construction value is indirect. |
| 11 | 2605.24004 | KEEP | Keep | Closed-loop embodied LLM decision agent with world model verification. |
| 12 | 2605.23934 | DROP | Removed | Quantum CIM domain integration using LangGraph/LangChain, weak new agent mechanism. |
| 13 | 2605.25958 | BORDERLINE | Keep | Agentic harness engineering analysis, but financial OSINT application heavy. |
| 14 | 2605.25200 | KEEP | Keep | Benchmark for multi-person, multi-turn LLM travel-planning agents. |
| 15 | 2605.23917 | DROP | Removed | Battery-materials hypothesis generation app using multi-persona debate. |
| 16 | 2605.24202 | KEEP | Keep | Multi-agent RL for LLM workflows and policy sharing. |
| 17 | 2605.25815 | KEEP | Keep | Self-evolving agent-to-agent collaboration network analysis. |
| 18 | 2605.24423 | DROP | Removed | Ad-hoc teamwork / ICRL benchmark not clearly about LLM agents. |
| 19 | 2605.24197 | BORDERLINE | Keep | Agentic workflow failure analysis, but alignment/misalignment framing. |
| 20 | 2605.24516 | DROP | Removed | Generic MARL / game-theoretic cooperation, not LLM agents. |
| 21 | 2605.25604 | KEEP | Restored | Generic LLM RL/training optimization is in scope under the corrected GRPO/DAPO-style policy. |
| 22 | 2605.25511 | BORDERLINE | Keep | Role-playing agents, but mostly persona-style RL rather than core agent mechanism. |
| 23 | 2605.25381 | KEEP | Restored | Generic RLVR training optimization is in scope under the corrected policy. |
| 24 | 2605.25198 | BORDERLINE | Keep | Generic RLVR method with agentic search as one evaluation setting. |
| 25 | 2605.24547 | KEEP | Restored | LLM RL with learnable textual feedback is in scope as LLM training optimization. |
| 26 | 2605.25624 | KEEP | Keep | Verifiable RL environments and tasks for computer-use agents. |
| 27 | 2605.24539 | KEEP | Keep | Agentic harness evolution with demonstrations. |
| 28 | 2605.24052 | DROP | Removed | Crowdsourcing preference aggregation; multi-agent refers to strategic workers. |
| 29 | 2605.26099 | DROP | Removed | Model architecture / long-context memory, not persistent agent memory. |
| 30 | 2605.25869 | KEEP | Keep | Long-term agent typed memory representation. |
| 31 | 2605.25693 | KEEP | Keep | Role-playing agent dual memory and persona-conditioned memory. |
| 32 | 2605.24930 | DROP | Removed | Hierarchical memory transformer for long-context inference, not agent memory. |
| 33 | 2605.24647 | BORDERLINE | Keep | User-state modeling for multi-turn conversation; agent mechanism is implicit. |
| 34 | 2605.24005 | KEEP | Keep | Self-evolving reasoning via reward decomposition. |
| 35 | 2605.23986 | KEEP | Keep | Explicit LLM agent memory system. |
| 36 | 2605.24693 | KEEP | Keep | Feedback-driven competitive-programming agent. |
| 37 | 2605.24660 | KEEP | Keep | Tool shortlist sizing for LLM agents. |
| 38 | 2605.26086 | KEEP | Keep | Always-on personal assistant benchmark with GUI/CLI tools. |
| 39 | 2605.24953 | BORDERLINE | Keep | Industrial multi-agent dialog system; mechanism value exists but domain-heavy. |
| 40 | 2605.24096 | KEEP | Keep | Coding-agent system synthesis with iterative evaluation. |
| 41 | 2605.23914 | BORDERLINE | Keep | Runtime model choice for agentic workflows; near infrastructure boundary. |
| 42 | 2605.23916 | KEEP | Keep | Agent-facing tool registry information design. |
| 43 | 2605.26079 | KEEP | Keep | Agentic benchmark auditing for AI agents and LLMs. |
| 44 | 2605.24703 | BORDERLINE | Keep | Time-series QA benchmark built with agentic generation/verification framework. |
| 45 | 2605.26087 | KEEP | Keep | Interactive scientific discovery benchmark for LLM agents. |
| 46 | 2605.25160 | KEEP | Keep | GUI agent simulation and benchmark environment. |
| 47 | 2605.25246 | BORDERLINE | Keep | LLM algorithm-design benchmark; coding agents/test-time evolution are evaluation settings. |
| 48 | 2605.24110 | KEEP | Keep | Multi-turn coding-agent benchmark under iterative changes. |
| 49 | 2605.24426 | KEEP | Keep | Co-evolution of tool-use agents and learning environments. |
| 50 | 2605.26081 | KEEP | Keep | Deep research agents with evolving mental models. |
| 51 | 2605.25430 | KEEP | Keep | Self-evolving procedural skills for coding agents. |
| 52 | 2605.24002 | DROP | Removed | Human-curated atomistic skill/tool harness; domain infrastructure, not self-evolving agent mechanism. |
| 53 | 2605.24117 | KEEP | Keep | Agent skill evolution benchmark from episodic experience to procedural skills. |
| 54 | 2605.25920 | KEEP | Keep | RL-trained legal agentic search with temporal consistency mechanism. |
| 55 | 2605.26029 | KEEP | Keep | Interactive causal discovery environment for AI scientist agents. |
| 56 | 2605.25998 | DROP | Removed | Broad causal methods for LLM development/evaluation; agent workflow only one application. |
| 57 | 2605.24828 | KEEP | Keep | Thinker-actor test-time exploration for agents in implicit-rule environments. |
| 58 | 2605.24598 | KEEP | Keep | Long-horizon device-cloud coordination for LLM agents. |
| 59 | 2605.24396 | KEEP | Restored | LLM reasoning/RL confidence shaping is retained as generic LLM training work. |
| 60 | 2605.24219 | KEEP | Keep | Trajectory-level hallucination auditing for multi-agent workflows. |
| 61 | 2605.24755 | DROP | Removed | Clinical NLP application using multi-agent LLM adjudication. |
