# Filter Recall Audit: 2026-05-16 to 2026-05-29

Audit date: 2026-05-31

Scope:
- Local raw candidates from `2026-05-16` through `2026-05-29`.
- `2026-05-27_to_2026-05-29` was missing locally and was crawled for audit only. It was not filtered, summarized, published, committed, or pushed.
- Keyword exclusions were not the main target, per operator guidance. The audit focused on post-keyword API/topic filtering, prestige filtering, timeouts, caps, and unpublished selected papers.

## Counts

- Raw papers in scope: 5,251
- Published papers in scope: 40
- Retry-needed stale exclusions detected by the repaired schema gate: 300
- Selected but not published: 62
- Selection-cap exclusions: 13
- Prestige exclusions still worth manual review: 82
- Topic exclusions: 1,019
- Newly crawled, unprocessed raw papers for 2026-05-27 to 2026-05-29: 1,703

## Highest-Risk Misses

These are the papers most likely to be relevant but not visible on the published pages.

### Retry Needed

These were often strong topic hits, but old cache entries encoded timeouts or affiliation extraction failures as finished exclusions. They should be reprocessed, not trusted as final rejects.

- `2605.21768` - Memory-R2: Fair Credit Assignment for Long-Horizon Memory-Augmented LLM Agents
- `2605.17281` - ContractBench: Can LLM Agents Preserve Observation Contracts?
- `2605.17873` - HINT-SD: Targeted Hindsight Self-Distillation for Long-Horizon Agents
- `2605.17734` - Harnessing LLM Agents with Skill Programs
- `2605.19782` - Prior Knowledge or Search? A Study of LLM Agents in Hardware-Aware Code Optimization
- `2605.22166` - Adapting the Interface, Not the Model: Runtime Harness Adaptation for Deterministic LLM Agents
- `2605.20061` - Rewarding Beliefs, Not Actions: Consistency-Guided Credit Assignment for Long-Horizon Agents
- `2605.22154` - IdleSpec: Exploiting Idle Time via Speculative Planning for LLM Agents
- `2605.16986` - Skills on the Fly: Test-Time Adaptive Skill Synthesis for LLM Agents
- `2605.18693` - SkillGenBench: Benchmarking Skill Generation Pipelines for LLM Agents
- `2605.18882` - To Call or Not to Call: Diagnosing Intrinsic Over-Calling Bias in LLM Agents
- `2605.21347` - Insights Generator: Systematic Corpus-Level Trace Diagnostics for LLM Agents

### Selected But Unpublished

These had already passed filtering in local artifacts, but did not appear in published pages because the surrounding run failed or remained unpublished.

- `2605.17641` - Causal Intervention-Based Memory Selection for Long-Horizon LLM Agents
- `2605.16045` - RecMem: Recurrence-based Memory Consolidation for Efficient and Effective Long-Running LLM Agents
- `2605.25480` - Retrieval as Reasoning: Self-Evolving Agent-Native Retrieval via LLM-Wiki
- `2605.25430` - CODESKILL: Learning Self-Evolving Skills for Coding Agents
- `2605.25200` - GroupTravelBench: Benchmarking LLM Agents on Multi-Person Travel Planning
- `2605.25815` - Behind EvoMap: Characterizing a Self-Evolving Agent-to-Agent Collaboration Network
- `2605.24660` - How Many Tools Should an LLM Agent See? A Chance-Corrected Answer
- `2605.25981` - When Do LLM Agents Treat Surface Noise Differently from Semantic Noise?
- `2605.23986` - MemForest: An Efficient Agent Memory System with Hierarchical Temporal Indexing
- `2605.25869` - Mitigating Provenance-Role Collapse in Long-Term Agents via Typed Memory Representation

### Selection-Cap Misses

These passed topic and prestige checks but were removed by the daily output cap. The top four look genuinely worth reading.

- `2605.16143` - Look Before You Leap: Autonomous Exploration for LLM Agents
- `2605.15573` - Response-Conditioned Parallel-to-Sequential Orchestration for Multi-Agent Systems
- `2605.15343` - Belief Engine: Configurable and Inspectable Stance Dynamics in Multi-Agent LLM Deliberation
- `2605.15224` - ICRL: Learning to Internalize Self-Critique with Reinforcement Learning

### Prestige Misses

These are strong topic matches that failed the prestige gate. Several were excluded only because affiliation extraction or deterministic whitelist matching did not supply enough evidence.

- `2605.16233` - FORGE: Self-Evolving Agent Memory With No Weight Updates via Population Broadcast
- `2605.24941` - Memory-Induced Tool-Drift in LLM Agents
- `2605.25535` - Personalize-then-Store: Benchmarking and Learning Personalized Memory for Long-horizon Agents
- `2605.24279` - ContextEcho: A Benchmark for Persona Drift in Long Agentic-Coding Sessions
- `2605.25310` - Tool-Call Dependency Structure is Linearly Decodable in LLM Agent Residual Streams
- `2605.23950` - Stop Comparing LLM Agents Without Disclosing the Harness
- `2605.23929` - Toward Reliable Design of LLM-Enabled Agentic Workflows: Optimizing Latency-Reliability-Cost Tradeoffs
- `2605.26112` - From Model Scaling to System Scaling: Scaling the Harness in Agentic AI

### Newly Crawled Unprocessed Papers

These are not misses from API filtering yet; they were absent from local raw data before this audit. They should be processed in a normal closed publication run.

- `2605.26720` - Towards Feedback-to-Plan Decisions for Self-Evolving LLM Agents in CUDA Kernel Generation
- `2605.28224` - When Does Memory Help Multi-Trajectory Inference for Tool-Use LLM Agents?
- `2605.28840` - How Consistent Are LLM Agents? Measuring Behavioral Reproducibility in Multi-Step Tool-Calling Pipelines
- `2605.27366` - MUSE-Autoskill: Self-Evolving Agents via Skill Creation, Memory, Management, and Evaluation
- `2605.30159` - Meta-Cognitive Memory Policy Optimization for Long-Horizon LLM Agents
- `2605.26186` - SetupX: Can LLM Agents Learn from Past Failures in Functionality-Correct Code Repository Setup?
- `2605.29440` - SkillBrew: Multi-Objective Curation of Skill Banks for LLM Agents
- `2605.29225` - BenchTrace: A Benchmark for Testing Reflection Ability and Controlled Evolution in LLM Agents
- `2605.29874` - Evolutionary Dynamics of Cooperation in Next-Generation LLM Agent Systems

## Code Follow-Up Applied

- Legacy timeout exclusions are now stale and retried, even if older runs saved them as `exclude_stage=topic`.
- Prestige affiliation extraction failures are now retryable filter failures instead of hard prestige rejects.
- Any filtering timeout remains publication-blocking.
- Strong deterministic topic hits can skip the brittle second topic LLM pass when they do not contain hard exclusion-domain terms.
- Daily automation no longer enables topic-heuristic prestige bypass by default; legacy `topic_heuristic_bypass` outputs are stale under the new rule version.
- Publication validation now rejects legacy topic-only prestige bypass papers when the hard prestige gate is active.
- Topic scoring no longer penalizes titles containing plural `agents`.
- Added tests for timeout cache invalidation, extraction-failure cache invalidation, coding-agent heuristic coverage, strong topic bypass, and security-topic adjudication.
