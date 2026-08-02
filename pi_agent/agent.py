"""
Pi-Agent 核心 — 自主文献调研 Agent 主循环
==========================================
基于 ReAct 模式（Think → Act → Observe）的自动化文献调研系统。

架构层次：
  Layer 1: LLMClient — DeepSeek API 调用抽象
  Layer 2: PiAgent  — 事件驱动 + 状态机 + 工具管线 + 会话持久化 + 上下文压缩

Agent 在预算内自主完成四阶段流程：
  阶段1: 文献检索（多源并发搜索 + 相关性筛选）
  阶段2: 知识抽取（正则快提 → LLM 精提 → 知识图谱融合）
  阶段3: Gap 分析（矛盾检测 / 缺失连接 / 未探索空间 / 新颖性评分）
  阶段4: 报告生成（结构化 Markdown + JSON + 证据链）

每轮循环：LLM 分析局势 → 决定行动 → 执行工具 → 观察结果 → 更新记忆 → 进入下一轮
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from pi_agent.events import (
    Event, EventBus,
    EVENT_AGENT_START, EVENT_AGENT_END,
    EVENT_TURN_START, EVENT_TURN_END,
    EVENT_TOOL_START, EVENT_TOOL_END,
    make_logging_listener,
)
from pi_agent.llm import LLMClient
from pi_agent.state_machine import StateMachine, AgentState
from pi_agent.session import SessionManager
from pi_agent.context import compress_messages
from pi_agent.tools import build_tool_manager


class PiAgent:
    """自主机器学习实验 Agent。

    核心设计：
      - 事件驱动：所有关键生命周期节点发出事件，便于日志记录和扩展
      - 状态机：RUNNING → TOOL_EXECUTING → RUNNING → ... → DONE，含状态钩子
      - 工具管线：define → register → intercept → execute → recycle
      - 会话管理：保存/恢复完整对话状态，支持中断后恢复
      - 上下文压缩：长对话自动压缩，保持在 LLM 上下文窗口内
      - 预算追踪：实时监控时间消耗，到期自动提醒收尾
    """

    def __init__(self, output_dir: str = "workspace/outputs/",
                 budget: int = None, fresh_start: bool = False,
                 research_topic: str = ""):
        """初始化文献调研 Agent。

        参数:
            output_dir: 输出根目录
            budget: 时间预算（秒），默认从配置读取 7200（2小时）
            fresh_start: True 则删除已有 checkpoint，强制从头开始
            research_topic: 文献调研主题
        """
        self.task_type = "survey"
        self.output_dir = output_dir
        self.bench = "A"  # 保持兼容
        self._stop_requested = False
        self.research_topic = research_topic

        # ── 时间预算追踪 ──
        from utils.budget_tracker import BudgetTracker
        from utils.config import TOTAL_BUDGET_SECONDS, SAFETY_MARGIN_SECONDS
        if budget is not None:
            self.budget = BudgetTracker(total_budget=budget, safety_margin=SAFETY_MARGIN_SECONDS)
        else:
            self.budget = BudgetTracker(total_budget=TOTAL_BUDGET_SECONDS, safety_margin=SAFETY_MARGIN_SECONDS)

        # ── 事件总线：解耦各模块通信 ──
        self.events = EventBus()
        self.events.on_any(make_logging_listener(self._print))

        # ── 状态机：管理 Agent 生命周期状态 ──
        self.state_machine = StateMachine()
        self._setup_state_hooks()

        # ── LLM 客户端：通过 DeepSeek API 进行推理决策 ──
        self.llm = LLMClient(print_fn=self._print)

        # ── 会话管理：支持中断恢复（checkpoint） ──
        self.session = SessionManager("survey")

        # ── 调研记忆：记录每次调研的发现、Gap、分析 ──
        self._memory_dir = Path("workspace/memory/survey")
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._memory_index = self._memory_dir / "MEMORY.md"
        self._protect_memory_index()

        # ── 工具管线：Agent 可调用的所有工具（读写文件、启停脚本等） ──
        self._tool_manager, self._tool_handlers = build_tool_manager(
            task_type="survey", bench="A", memory_dir=self._memory_dir,
            print_fn=self._print, event_bus=self.events,
        )
        self._tool_handlers._on_stop = self._handle_stop
        self._tool_handlers._on_think = self._handle_think

        # ── 清理上次运行的临时文件 ──
        self._cleanup_workspace()

        if fresh_start:
            self.session.delete()
            # 清理上次运行的 checkpoint 文件，避免 Agent 产生困惑
            import glob as _g2
            for stale in _g2.glob("workspace/checkpoint_*.json") + _g2.glob("workspace/logs/trajectory_*.json"):
                try: os.remove(stale)
                except OSError: pass

        # ── 核心运行时状态 ──
        self._user_goal = ""               # 用户目标描述
        self._compression_summary = ""     # 上下文压缩后的摘要
        self._last_experiment_done = False # 上一轮训练是否刚完成（触发反思）
        self._last_agent_thinking = ""     # Agent 最近一次的思考内容
        self._messages: List[Dict] = []    # LLM 对话历史
        self._recent_outputs: List[str] = [] # 最近的 shell 输出（用于异常检测）
        self._trajectory: List[Dict] = []  # 实验轨迹日志
        self._experiments_completed = 0    # 已完成阶段计数
        if self._memory_dir.exists():
            self._experiments_completed = len(list(self._memory_dir.glob("survey-*.md")))

    # ═══════════════════════════════════════════════════════════
    # 初始化辅助方法
    # ═══════════════════════════════════════════════════════════

    def _setup_state_hooks(self):
        """在状态转移上挂载钩子函数。"""

        def _on_enter_running():
            pass

        def _on_enter_tool_executing():
            pass

        def _on_enter_done():
            self._print(f"\n🏁 Agent entering DONE state — finalizing...")

        self.state_machine.on_enter(AgentState.RUNNING, _on_enter_running)
        self.state_machine.on_enter(AgentState.TOOL_EXECUTING, _on_enter_tool_executing)
        self.state_machine.on_enter(AgentState.DONE, _on_enter_done)

    def _protect_memory_index(self):
        """MEMORY.md 损坏时从备份恢复。防止索引丢失导致历史实验无法读取。"""
        bak_path = self._memory_dir / "MEMORY.md.bak"
        if not self._memory_index.exists() or self._memory_index.stat().st_size < 50:
            if bak_path.exists() and bak_path.stat().st_size > 100:
                import shutil
                shutil.copy2(str(bak_path), str(self._memory_index))
                self._print(f"  🛡️ MEMORY.md restored from backup ({bak_path.stat().st_size} bytes)")
            elif not self._memory_index.exists():
                self._memory_index.write_text(f"# Agent Experiment Memory — {self.task_type}\n\n", encoding="utf-8")

    def _cleanup_workspace(self):
        """清理上次运行残留的临时文件和迭代脚本。"""
        import glob as _g
        import shutil
        for f in _g.glob("workspace/code/iteration_*.py"):
            try: os.remove(f)
            except OSError: pass
        tmp_dir = Path("workspace/outputs/.tmp")
        if tmp_dir.exists():
            try: shutil.rmtree(tmp_dir)
            except OSError: pass
            tmp_dir.mkdir(parents=True, exist_ok=True)

    def _handle_stop(self):
        """Agent 调用 stop 工具时触发：标记停止请求。"""
        self._stop_requested = True

    def _handle_think(self, topic: str) -> str:
        """Agent 调用 think 工具时触发：做一次纯文本深度推理。

        复用当前对话上下文，但不产生 tool call，让 LLM 对特定话题做深入分析。
        """
        think_msg = {
            "role": "user",
            "content": (
                f"[深度思考]\n"
                f"主题：{topic}\n\n"
                f"请深入分析当前局势。考虑以下方面：\n"
                f"- 现有结果告诉我们什么？\n"
                f"- 可以形成什么假设？底层机制是什么？\n"
                f"- 存在哪些风险和替代方案？\n\n"
                f"进行透彻分析，然后给出明确的下一步建议及其理由。"
            )
        }
        # 构建纯文本消息列表（去掉 tool_calls 和对应的 tool 响应）
        # DeepSeek API 要求：role=tool 的消息必须前面有带 tool_calls 的 assistant 消息
        # 纯文本推理模式下必须同时去掉两者
        clean = []
        for m in self._messages:
            role = m.get("role", "")
            if role == "tool":
                # 跳过：tool 响应依赖 tool_calls，纯文本模式不需要
                continue
            elif "tool_calls" in m:
                # 保留 assistant 的思考内容，去掉 tool_calls 元数据
                clean.append({k: v for k, v in m.items() if k != "tool_calls"})
            else:
                clean.append(m)
        messages = clean + [think_msg]
        result = self.llm.think(messages, max_tokens=1200)
        self._print(f"     💭 {result[:300]}...")
        return result

    # ═══════════════════════════════════════════════════════════
    # 系统提示词构建
    # ═══════════════════════════════════════════════════════════

    def _build_system_prompt(self) -> str:
        """构建系统提示词。"""
        from pi_agent.prompts import SURVEY_SYSTEM_PROMPT
        return SURVEY_SYSTEM_PROMPT

    # ═══════════════════════════════════════════════════════════
    # 主循环 — ReAct 模式 (Think → Act → Observe)
    # ═══════════════════════════════════════════════════════════

    def run(self) -> Dict:
        """启动自主文献调研循环。

        ReAct 模式流程：
          1. LLM 思考（Think）：分析当前状态 → 决定下一步行动
          2. 执行工具（Act）：运行检索/抽取脚本、读写文件、监控进程
          3. 观察结果（Observe）：读取脚本输出 → 更新调研记忆
          4. 循环直到预算耗尽或 Agent 主动停止

        每轮记录写入 trajectory log，供评审核查调研过程。
        """
        self.budget.start()
        self.events.emit(Event(EVENT_AGENT_START, {"task": self.task_type, "bench": self.bench}))

        self._print(f"\n{'='*60}")
        self._print(f"🔬 Pi-Agent: {self.task_type}")
        self._print(f"{'='*60}")
        self._print(f"  Budget: {self.budget.total_budget}s | "
                    f"Model: {self.llm._active_provider.model} ({self.llm.active_provider_name})")
        self._print(f"  Architecture: Pi-Agent (event-driven + state machine + tool pipeline)")
        self._print(f"{'='*60}")

        # ── 加载 checkpoint 或全新开始 ──
        start_iter = 0
        if self.session.exists():
            ckpt = self.session.load()
            if ckpt:
                self._print(f"  🔄 Resuming from checkpoint: iter={ckpt['iteration']}")
                start_iter = ckpt["iteration"]
                self._compression_summary = ckpt.get("summary", "")
                self.budget.start_time -= ckpt.get("budget_elapsed", 0)
                self._messages = ckpt.get("messages", [])
                self._trajectory = ckpt.get("trajectory", [])
                self._experiments_completed = ckpt.get("experiments_completed", 0)
                self._print(f"      Restored {len(self._messages)} messages, {len(self._trajectory)} trajectory entries")

        # ── 构建初始消息 ──
        if start_iter == 0:
            self._user_goal = (
                f"调研主题：{self.research_topic}。\n"
                f"📖 第零步（每次运行必须先执行！）：\n"
                f"1) read_file workspace/memory/survey/MEMORY.md — 检查是否有历史调研记录\n"
                f"2) read_file workspace/feedback/survey.md — 检查评审反馈（如有）\n"
                f"3) list_files workspace/data/literature_cache/ — 查找缓存的论文和搜索日志\n"
                f"4) list_files workspace/code/survey/ — 查找已有的搜索/抽取脚本\n"
                f"⚠️ 如果 MEMORY.md 已有调研记录：从已知的最佳知识图谱开始继续。\n"
                f"⚠️ 如果是首次调研（空记忆）：执行完整的四阶段流程。\n"
                f"所有搜索/抽取脚本由你编写（write_file）并通过 start_shell 执行。\n"
                f"使用 literature_agent 包中的 search / parser / extractor / gap_analyzer / report_generator 模块。\n"
                f"收尾前，将记忆写入 workspace/memory/survey/ 并更新 MEMORY.md。\n"
                f"所有思考和输出请使用中文。\n"
            )
            start_iter = 1

        if not self._messages:
            system_prompt = self._build_system_prompt()
            # 提示 Agent 历史实验/调研记忆的位置
            hints = []
            if self._memory_index.exists():
                hints.append(
                    f"历史记忆文件位于 `{self._memory_index}`。"
                    f"**请使用 read_file 工具自行读取**。"
                )
            roadmap_path = Path(f"workspace/memory/{self.task_type}/exploration_roadmap.md")
            if roadmap_path.exists():
                hints.append(
                    f"探索路线图位于 `{roadmap_path}`。"
                    f"**请使用 read_file 工具自行读取**。"
                )
            if hints:
                system_prompt += "\n\n## 🧠 Historical Experiment Memory\n" + "\n\n".join(hints) + "\n"

            self._messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._user_goal},
            ]

        # 上下文压缩后的摘要注入
        if self._compression_summary and start_iter > 1:
            self._messages.insert(1, {
                "role": "user",
                "content": f"[Previous round summary]\n{self._compression_summary}\n\nContinue experimenting; do not repeat work already done."
            })

        # ── 检查 API 可用性 ──
        if not self.llm.available:
            self._print(f"\n❌ No LLM provider available. Exiting.")
            self.events.emit(Event(EVENT_AGENT_END, {"reason": "no_api"}))
            return {}

        # ═══════════════════════════════════════════════════
        # ReAct 主循环
        # ═══════════════════════════════════════════════════
        self.state_machine.transition(AgentState.RUNNING)
        iteration = start_iter
        budget_final_warning_given = False

        while not self._stop_requested:
            # ── 预算耗尽检查 ──
            if self.budget.must_stop_now():
                if not budget_final_warning_given:
                    self._messages.append({
                        "role": "user",
                        "content": (
                            f"⏰ 预算已耗尽，请勿搜索新论文。请完成以下收尾工作：\n"
                            f"1) 生成调研报告到 workspace/outputs/literature_survey/\n"
                            f"2) write_file 记忆到 workspace/memory/survey/ 并更新 MEMORY.md\n"
                            f"3) 调用 stop 工具结束本次调研\n"
                        )
                    })
                    budget_final_warning_given = True
                    self._print(f"\n⏰ Budget exhausted, waiting for Agent to wrap up...")

            iteration += 1
            elapsed_before = self.budget.elapsed()

            self.events.emit(Event(EVENT_TURN_START, {
                "iteration": iteration,
                "budget_elapsed": elapsed_before,
                "budget_remaining": self.budget.remaining(),
            }))
            self._print(f"\n─ Iteration #{iteration} | Elapsed {elapsed_before:.0f}s ─")

            # ── 反思触发：上一阶段刚完成，强制 Agent 分析结果 ──
            if self._last_experiment_done:
                self._messages.append({
                    "role": "user",
                    "content": (
                        "[反思] 上一阶段刚刚完成。在开始任何新工作之前：\n"
                        "1. 结果是否符合你的假设？为什么（不）符合？\n"
                        "2. 你学到了什么之前不知道的东西？\n"
                        "3. 下一步计划是否仍然合理？必要时调整策略。\n\n"
                        "将简要反思写入 workspace/memory/survey/survey-reflection.md，然后继续。"
                    )
                })
                self._last_experiment_done = False

            # ── 阶段 1: LLM 调用（Think） ──
            t_api_start = time.time()
            content, reasoning, tool_calls_raw = self.llm.call_with_tools(self._messages)
            t_api_elapsed = time.time() - t_api_start

            remaining = self.budget.remaining()
            # 用比例判断而非绝对值，避免小预算时一直误报
            hint = " ⏳ 时间充裕" if self.budget.budget_used_pct() < 75 else " ⚠️ 时间紧张，准备收尾"
            self._print(f"     API time {t_api_elapsed:.1f}s | Remaining {remaining:.0f}s{hint}")

            if content is None and tool_calls_raw is None:
                self._print(f"  ❌ LLM call failed completely — stopping")
                self._stop_requested = True
                break

            # 显示 Agent 的思考内容
            thinking_text = content or reasoning or ""
            if thinking_text.strip():
                self._last_agent_thinking = thinking_text
            if content:
                self._print(f"\n{'─'*50}\n🧠 Agent:\n   {content}\n{'─'*50}")
            elif reasoning:
                self._print(f"\n{'─'*50}\n🧠 Agent:\n   {reasoning[:500]}\n{'─'*50}")

            # 将 LLM 响应加入对话历史
            assistant_msg = {
                "role": "assistant",
                "content": content or "",
                "reasoning_content": reasoning or "",
            }
            if tool_calls_raw:
                assistant_msg["tool_calls"] = tool_calls_raw
            self._messages.append(assistant_msg)

            if not tool_calls_raw:
                continue

            # ── 阶段 2: 执行工具（Act） ──
            self.state_machine.transition(AgentState.TOOL_EXECUTING)

            round_tools_list = []
            round_feedback = {}

            results = self._tool_manager.execute_sequential(tool_calls_raw)

            for tc_raw, result_str in results:
                fn = tc_raw.get("function", {})
                tool_name = fn.get("name", "?")

                self._fmt_tool_result(tool_name, result_str)

                try:
                    args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                except Exception:
                    args = {}

                # 工具结果加入对话历史（LLM 下次调用时可见）
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc_raw.get("id", "call_0"),
                    "content": result_str,
                })

                # 记录工具调用摘要（用于轨迹日志）
                tool_summary = {"tool": tool_name}
                if tool_name == "read_file":
                    tool_summary["file"] = args.get("filepath", "")[:120]
                elif tool_name in ("write_file", "edit_file"):
                    tool_summary["file"] = args.get("file_path", args.get("filepath", ""))[:120]
                elif tool_name == "start_shell":
                    tool_summary["command"] = args.get("command", "")[:120]
                elif tool_name == "check_shell":
                    tool_summary["pid"] = args.get("pid", "?")
                elif tool_name == "kill_shell":
                    tool_summary["pid"] = args.get("pid", "?")
                elif tool_name == "stop":
                    tool_summary["action"] = "stop"
                round_tools_list.append(tool_summary)

                # 缓存 shell 输出用于异常检测
                if tool_name in ("check_shell", "run_shell"):
                    self._recent_outputs.append(str(result_str))
                    if len(self._recent_outputs) > 20:
                        self._recent_outputs = self._recent_outputs[-15:]

                # ── 检测实验是否完成 ──
                _is_experiment = False
                result_str_lower = str(result_str).lower()
                _has_metrics = any(kw in result_str for kw in (
                    "NDCG", "Accuracy", "Best", "Done", "最优", "全部完成"
                ))
                _has_error = any(kw in result_str_lower for kw in (
                    "traceback", "error:", "nameerror", "keyerror",
                    "attributeerror", "syntaxerror", "runtimeerror", "cuda error"
                ))
                if tool_name == "check_shell" and _has_metrics:
                    _is_experiment = True
                elif tool_name == "run_shell":
                    _is_experiment = _has_metrics and not _has_error
                if _is_experiment:
                    self._experiments_completed += 1
                    self._last_experiment_done = True  # 下一轮触发反思
                    self._print(f"  📊 Experiment #{self._experiments_completed} completed")

            # ── 构建轨迹日志条目 ──
            thinking = self._last_agent_thinking[:500] if self._last_agent_thinking else ""
            if not thinking and round_tools_list:
                tool_names = [t["tool"] for t in round_tools_list]
                thinking = f"[Tool calls: {', '.join(tool_names[:5])}]"

            # 从思考中提取策略摘要
            strategy = ""
            if thinking:
                sentences = [s.strip() for s in thinking.replace("\n", " ").split("。") if s.strip()]
                strategy = "。".join(sentences[-2:]) if len(sentences) >= 2 else (sentences[-1] if sentences else thinking[:200])

            round_config = self._extract_round_config(thinking_text, round_tools_list, round_feedback)

            self._trajectory.append({
                "round": len(self._trajectory) + 1,
                "iteration": iteration,
                "agent_thinking": thinking,
                "config": round_config if round_config else None,
                "feedback": round_feedback if round_feedback else None,
                "strategy": strategy if strategy else None,
                "tools_called": round_tools_list,
                "budget_remaining": int(self.budget.remaining()),
            })
            self._save_trajectory()

            self.events.emit(Event(EVENT_TURN_END, {
                "iteration": iteration,
                "tools_executed": len(round_tools_list),
            }))

            # ── 会话 checkpoint：支持中断后恢复 ──
            self.session.save(
                iteration=iteration, messages=self._messages,
                budget_elapsed=self.budget.elapsed(),
                summary=self._compression_summary,
                trajectory=self._trajectory,
                experiments_completed=self._experiments_completed,
            )

            self.state_machine.transition(AgentState.RUNNING)

            # ── 预算提醒：每 5 轮或达到阈值时通知 Agent ──
            remaining = self.budget.remaining()
            pct = remaining / self.budget.total_budget * 100
            if not hasattr(self, '_budget_pcts_seen'):
                self._budget_pcts_seen = set()
            budget_msg = None
            if iteration % 5 == 0:
                budget_msg = (
                    f"⏰ 预算状态：已用 {self.budget.elapsed():.0f}s / 总计 {self.budget.total_budget}s，"
                    f"剩余 {remaining:.0f}s（{pct:.0f}%）。剩余 <300s 时请收尾。"
                )
            for threshold in [50, 25, 10]:
                if pct < threshold and threshold not in self._budget_pcts_seen:
                    self._budget_pcts_seen.add(threshold)
                    budget_msg = (
                        f"⏰⚠️ 仅剩 {remaining:.0f}s（{pct:.0f}%）预算！"
                        f"必须收尾：生成报告、写入记忆、调用 stop。"
                    )
                    break
            if budget_msg:
                self._messages.append({"role": "user", "content": budget_msg})
                self._print(f"  ⏰ {budget_msg}")

            # ── 上下文压缩：对话过长时自动压缩 ──
            _total_chars = sum(len(str(m.get("content", ""))) for m in self._messages)
            if _total_chars > 3_500_000:
                self._messages = compress_messages(
                    messages=self._messages,
                    trajectory=self._trajectory,
                    experiments_completed=self._experiments_completed,
                    compression_summary=self._compression_summary,
                    print_fn=self._print,
                )
                reminder = (
                    f"上下文已压缩。请重新 read_file {self._memory_index} 了解全局实验状态，"
                    f"并按需读取具体记忆文件。已完成 {self._experiments_completed} 个实验阶段。"
                )
                self._messages.append({"role": "user", "content": reminder})

        # ── 收尾：保存轨迹、清理 session ──
        self._print(f"\n🏁 Experiment ended | {len(self._trajectory)} rounds")
        self.state_machine.transition(AgentState.DONE)
        self.events.emit(Event(EVENT_AGENT_END, {"total_rounds": len(self._trajectory)}))

        self._save_trajectory()
        self.session.delete()

        return self._find_output_csv()

    # ═══════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════

    def _fmt_tool_result(self, name: str, result: str):
        """格式化输出工具执行结果（避免刷屏）。"""
        lines = result.strip().split("\n")
        if name == "list_files":
            count = len([l for l in lines if l.strip()])
            self._print(f"     → Found {count} files")
            for line in lines[:8]:
                self._print(f"       {line}")
            if count > 8:
                self._print(f"       ... {count - 8} more files")
        elif name == "read_file":
            preview = result[:200].replace("\n", " ")
            self._print(f"     → {preview}...")
        elif name == "write_file" and "✅" in result:
            for line in result.strip().split("\n"):
                line = line.strip()
                if line:
                    self._print(f"     {line}")
        elif name == "start_shell":
            preview = result[:200].replace("\n", " ")
            self._print(f"     → {preview}")
        elif name == "check_shell":
            non_empty = [l for l in result.split("\n") if l.strip()]
            for line in non_empty[-6:]:
                self._print(f"       {line[:150]}")
        elif name == "kill_shell":
            preview = result[:200].replace("\n", " ")
            self._print(f"     → {preview}")
        elif name == "stop":
            self._print(f"     🛑 Experiment ended")
        else:
            preview = result[:200].replace("\n", " ")
            self._print(f"     → {preview}")

    def _save_trajectory(self):
        """持久化调研轨迹日志到磁盘。"""
        try:
            path = "workspace/logs/trajectory_survey.json"
            os.makedirs("workspace/logs", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "task": "survey",
                    "agent_type": "pi-agent",
                    "total_rounds": len(self._trajectory),
                    "trajectory": self._trajectory,
                }, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            self._print(f"  ⚠️ Trajectory save failed: {e}")

    def _find_output_csv(self) -> Dict:
        """查找 Agent 生成的调研报告。"""
        report_path = Path("workspace/outputs/literature_survey/survey_report.md")
        if report_path.exists():
            self._print(f"  ✅ Found survey report ({report_path})")
        return {}

    @staticmethod
    def _extract_round_config(thinking_text: str, round_tools: list, round_feedback: dict) -> Optional[Dict]:
        """从 Agent 思考文本中提取结构化配置信息（轨迹日志用）。"""
        config = {}

        # ── 搜索关键词识别 ──
        search_kw = re.findall(r'(?:search|query|检索)[:\s]*["\']?([^"\'\n]{5,100})["\']?', thinking_text, re.IGNORECASE)
        if search_kw:
            config["search_queries"] = search_kw[:5]

        # ── 发现的实体 ──
        for label, patterns in [
            ("materials", [r'(?:material|材料)[:\s]*([A-Z][a-z]?[0-9A-Za-z]{1,20})']),
            ("properties", [r'(?:property|性质)[:\s]*(band gap|conductivity|PCE|stability|efficiency)[\w\s]*']),
        ]:
            seen = set()
            for pat in patterns:
                for m in re.findall(pat, thinking_text, re.IGNORECASE):
                    seen.add(m.strip())
            if seen:
                config[label] = sorted(seen)[:10]

        # ── 修改的文件名 ──
        touched = []
        for t in round_tools:
            if t.get("tool") in ("write_file", "edit_file"):
                fp = t.get("file", "")
                if fp:
                    touched.append(fp)
        if touched:
            config["touched_files"] = touched

        if round_feedback:
            config["feedback"] = round_feedback

        return config if config else None

    def _print(self, msg: str):
        print(msg, flush=True)
