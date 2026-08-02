"""
工具系统 — Pi-Agent Layer 2
============================
Agent 通过工具与外部环境交互。每个工具经过五步管线处理：

  1. DEFINE   — 定义工具 schema（名称、参数、描述）
  2. REGISTER — 注册工具名 → 处理函数的映射
  3. INTERCEPT — 执行前后钩子（可拦截或修改调用）
  4. EXECUTE   — 调用处理函数，捕获结果
  5. RECYCLE   — 执行后清理（如保存轨迹日志）

执行模式：
  - sequential（默认）：工具逐个执行，前一个结果对后续可见
  - parallel：工具并发执行（仅用于独立的读取操作）
"""
from __future__ import annotations

import json
import os
import re
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pi_agent.events import Event, EventBus, EVENT_TOOL_START, EVENT_TOOL_END

# ── Low-level tool implementations ──


class ToolManager:
    """
    Manages tool lifecycle: register → intercept → execute → recycle.

    Each tool handler receives (args: dict) and returns str.
    """

    def __init__(self, event_bus: EventBus = None, print_fn: Callable = None):
        self._handlers: Dict[str, Callable[[dict], str]] = {}
        self._before_hooks: List[Callable[[str, dict], Optional[str]]] = []
        self._after_hooks: List[Callable[[str, dict, str], str]] = []
        self._event_bus = event_bus
        self._print = print_fn or (lambda x: None)

    def register(self, name: str, handler: Callable[[dict], str]) -> None:
        """Register a tool handler function."""
        self._handlers[name] = handler

    def add_before_hook(self, hook: Callable[[str, dict], Optional[str]]) -> None:
        """
        Add a before-execution hook.
        Args:
            hook(tool_name, args) → None (allow) or str (block with this error message).
        """
        self._before_hooks.append(hook)

    def add_after_hook(self, hook: Callable[[str, dict, str], str]) -> None:
        """
        Add an after-execution hook.
        Args:
            hook(tool_name, args, result) → modified_result_str.
        """
        self._after_hooks.append(hook)

    # ── Execution ──

    def execute_sequential(self, tool_calls: List[Dict]) -> List[Tuple[Dict, str]]:
        """
        Execute tool calls one-by-one in order.
        Returns list of (tool_call_dict, result_string).
        """
        results: List[Tuple[Dict, str]] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "?")
            try:
                args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
            except (json.JSONDecodeError, TypeError) as e:
                # Try JSON repair
                raw = fn["arguments"] if isinstance(fn["arguments"], str) else ""
                from pi_agent.llm import LLMClient
                repaired = LLMClient.repair_json(raw)
                if repaired != raw:
                    try:
                        args = json.loads(repaired)
                        fn["arguments"] = repaired
                        self._print(f"  🔧 JSON auto-repair succeeded")
                    except Exception:
                        args = {"_json_error": str(e)[:200], "_raw_preview": raw[:500], "_raw_len": len(raw)}
                else:
                    args = {"_json_error": str(e)[:200], "_raw_preview": raw[:500], "_raw_len": len(raw)}

            result = self._execute_one(name, args, tc)
            results.append((tc, result))
        return results

    def _execute_one(self, tool_name: str, args: dict, raw_tc: Dict) -> str:
        """Execute a single tool call with hooks."""
        t0 = time.time()

        # Emit start event
        if self._event_bus:
            self._event_bus.emit(Event(EVENT_TOOL_START, {
                "tool_name": tool_name,
                "tool_args_summary": self._fmt_args(tool_name, args),
                "tool_call_id": raw_tc.get("id", ""),
            }))

        # Before hooks
        for hook in self._before_hooks:
            block_msg = hook(tool_name, args)
            if block_msg is not None:
                return block_msg

        # Execute
        handler = self._handlers.get(tool_name)
        if handler:
            try:
                result = handler(args)
            except Exception:
                result = f"ERROR: {traceback.format_exc()}"
        else:
            result = f"Unknown tool: {tool_name}"

        # Truncate large outputs
        result_str = str(result)
        if len(result_str) > 250_000:
            result_str = result_str[:250_000] + "\n...[truncated]"

        # After hooks
        for hook in self._after_hooks:
            result_str = hook(tool_name, args, result_str)

        # Emit end event
        if self._event_bus:
            self._event_bus.emit(Event(EVENT_TOOL_END, {
                "tool_name": tool_name,
                "duration_ms": (time.time() - t0) * 1000,
                "result_len": len(result_str),
            }))

        return result_str

    @staticmethod
    def _fmt_args(name: str, args: dict) -> str:
        """Format tool args for display."""
        if name == "list_files":
            d = args.get("directory", "workspace")
            p = args.get("pattern", "**/*")
            return f"📂 {d}/{p}"
        elif name == "read_file":
            fp = args.get("filepath", "")
            fname = fp.split("/")[-1] if "/" in fp else fp
            return f"📖 {fname}"
        elif name == "write_file":
            fp = args.get("filepath", "")
            fname = fp.split("/")[-1] if "/" in fp else fp
            return f"✏️  {fname}"
        elif name == "run_shell":
            return f"💻 {args.get('command', '')[:80]}"
        elif name == "start_shell":
            return f"🚀 {args.get('command', '')[:80]}"
        elif name == "check_shell":
            return f"🔍 pid={args.get('pid', '?')}"
        elif name == "kill_shell":
            return f"💀 pid={args.get('pid', '?')}"
        elif name == "stop":
            return "🛑 stop"
        return f"🔧 {name}"


# ═══════════════════════════════════════════════════════════════
# Tool Handler Implementations
# ═══════════════════════════════════════════════════════════════

class ToolHandlers:
    """
    All tool handler implementations. Separated from ToolManager so the
    Agent can inject its own state (task_type, output_dir, memory_dir, etc.).
    """

    def __init__(self, task_type: str, bench: str = "A",
                 memory_dir: Path = None, print_fn: Callable = None):
        self.task_type = task_type
        self.bench = bench
        self.memory_dir = memory_dir or Path(f"workspace/memory/{task_type}")
        self._print = print_fn or (lambda x: None)
        # State hooks (set by Agent)
        self._on_stop: Optional[Callable[[], None]] = None
        self._on_think: Optional[Callable[[str], str]] = None  # (topic) → analysis
        # Survey session state (accumulated across tool calls)
        self.survey_state: Dict[str, Any] = {}

    # ── think ──

    def h_think(self, args: dict) -> str:
        """Deep reasoning tool — invokes the LLM without tools for analysis."""
        topic = args.get("topic", "")
        if not topic:
            return "❌ think tool requires a 'topic' parameter describing what to analyze."
        if not self._on_think:
            return "❌ Think backend not configured."
        self._print(f"  💭 Thinking about: {topic[:100]}...")
        result = self._on_think(topic)
        if result:
            return f"## Analysis: {topic}\n\n{result}"
        return "⚠️ Think completed but produced no output."

    # ── list_files ──

    def h_list_files(self, args: dict) -> str:
        from pi_agent._tools_impl import list_files
        directory = args.get("directory", "workspace")
        pattern = args.get("pattern", "**/*")
        result = list_files(directory, pattern)
        lines = [f"{r['path']} ({r['size_kb']}KB)" for r in result.get("files", [])]
        out = "\n".join(lines) if lines else "(empty)"
        total = result.get("total_found", len(result.get("files", [])))
        shown = result.get("count", len(result.get("files", [])))
        if result.get("overflow"):
            out += (f"\n\n⚠️ Truncated: found {total} files total, only showing first {shown}."
                    f" Please narrow the pattern or specify a subdirectory and retry.")
        return out

    # ── read_file ──

    def h_read_file(self, args: dict) -> str:
        from pi_agent._tools_impl import read_file
        filepath = args["filepath"]
        data_exts = (".csv", ".tsv", ".npz", ".npy", ".parquet", ".pkl", ".pickle")
        is_data_file = any(filepath.lower().endswith(ext) for ext in data_exts)
        if is_data_file:
            self._print(f"  🛑 Data file protection: {filepath} only showing first 500 chars")
            result = read_file(filepath, max_chars=500)
            content = result.get("content", "(empty)")
            return content + "\n\n⚠️ [System forced truncation] Above only shows the file header. To analyze data, use write_file to write a script + run_shell to execute."
        result = read_file(filepath, max_chars=250000)
        if result.get("structure"):
            return json.dumps(result["structure"], ensure_ascii=False)
        return result.get("content", "(empty)")

    # ── write_file ──

    def h_write_file(self, args: dict) -> str:
        from pi_agent._tools_impl import write_file

        if "_json_error" in args:
            raw = args.get('_raw_preview', '')
            raw_len = args.get('_raw_len', len(raw))
            filepath_hint = raw.split('"filepath": "')[1].split('"')[0] if '"filepath": "' in raw else "?"
            if filepath_hint.lower().endswith(".md"):
                hint = f"Memory file is {raw_len} chars long, JSON escaping failed. Please condense the content."
            else:
                hint = f"Code file is {raw_len} chars long, JSON escaping failed. Please condense or split into multiple files."
            return (
                f"❌ JSON exploded: {hint}\n"
                f"Target file: {filepath_hint}\n"
                f"⚠️ Do NOT retry with content of the same length! It will NOT succeed!"
            )

        filepath = args.get("filepath", "")
        content = args.get("content", "")
        if not filepath:
            return "❌ write_file failed: missing filepath parameter."
        if not content:
            return "❌ write_file failed: missing content parameter (code content is empty)."

        # ⛔ Feedback files are read-only
        if "workspace/feedback/" in filepath.lower().replace("\\", "/"):
            return "⛔ Modifying feedback files is forbidden! Feedback is manually maintained by the user."

        # MEMORY.md pre-write backup
        mem_backup = None
        if filepath.lower().endswith("memory.md") and os.path.exists(filepath):
            try:
                mem_backup = open(filepath, "r", encoding="utf-8").read()
            except Exception:
                pass

        result = write_file(filepath, content, args.get("mode", "overwrite"))
        ftype = "py" if filepath.lower().endswith(".py") else "file"
        msg = f"✅ write_{ftype}: {filepath} ({len(content)} chars)"

# MEMORY.md auto-repair
        if filepath.lower().endswith("memory.md"):
            try:
                mem_dir = os.path.dirname(os.path.abspath(filepath))
                actual_files = sorted(
                    f for f in os.listdir(mem_dir)
                    if f.endswith(".md") and f != "MEMORY.md"
                )
                links_in_content = re.findall(r'\[([^\]]+)\]\(([^)]+\.md)\)', content)
                linked_files = {l[1] for l in links_in_content}
                missing = [f for f in linked_files if f not in actual_files]
                unlisted = [f for f in actual_files if f not in linked_files]
                if missing or unlisted:
                    rebuilt = [f"# Agent Experiment Memory — {self.task_type}\n"]
                    for fn in actual_files:
                        desc = None
                        for label, link in links_in_content:
                            if link == fn:
                                desc = label; break
                        if not desc:
                            desc = fn.replace(".md", "")
                        rebuilt.append(f"- [{desc}]({fn})")
                    corrected = "\n".join(rebuilt) + "\n"
                    write_file(filepath, corrected, "overwrite")
                    msg += (
                        f"\n\n⚠️ MEMORY.md auto-repair:\n"
                        + (f"  Wrong links (removed): {', '.join(missing)}\n" if missing else "")
                        + (f"  Missing files (added): {', '.join(unlisted)}" if unlisted else "")
                    )
            except Exception:
                pass

        # MEMORY.md content protection
        if filepath.lower().endswith("memory.md") and mem_backup is not None:
            try:
                new_content = open(filepath, "r", encoding="utf-8").read()
                if len(new_content.strip().split("\n")) < 5 and len(mem_backup.strip().split("\n")) >= 5:
                    open(filepath, "w", encoding="utf-8").write(mem_backup)
                    msg += "\n\n🛡️ MEMORY.md protection: Agent wrote too little, backup restored."
                else:
                    import shutil
                    shutil.copy2(filepath, filepath + ".bak")
            except Exception:
                pass

        return msg

    # ── edit_file ──

    def h_edit_file(self, args: dict) -> str:
        raw_path = args["file_path"]
        if not os.path.isabs(raw_path):
            if raw_path.startswith(("workspace/", "workspace\\", "predictors/", "predictors\\")):
                filepath = os.path.abspath(raw_path)
            else:
                filepath = os.path.abspath(os.path.join("workspace", raw_path))
        else:
            filepath = os.path.abspath(raw_path)

        # Block edits to core infrastructure
        blocked_prefixes = [
            os.path.abspath("agent"), os.path.abspath("pi_agent"),
            os.path.abspath("main.py"), os.path.abspath("utils"),
        ]
        for blocked in blocked_prefixes:
            if filepath.startswith(blocked):
                return f"⛔ Modifying core infrastructure is forbidden! {filepath} is in a protected area."

        if not os.path.exists(filepath):
            return f"❌ File does not exist: {filepath}"

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        patches = args.get("patches")
        if patches:
            patch_list = [(p["old_string"], p["new_string"]) for p in patches]
        elif args.get("old_string"):
            patch_list = [(args["old_string"], args["new_string"])]
        else:
            return "❌ edit_file failed: old_string+new_string or patches parameter required."

        replace_all = args.get("replace_all", False)
        total_replaced = 0

        for old_str, new_str in patch_list:
            count = content.count(old_str)
            if count == 0:
                return (f"❌ old_string not found in file! Use read_file to verify the file contents."
                        f"Note: old_string must match exactly (including indentation and whitespace).\n"
                        f"Preview of unfound content: {old_str[:100]}")
            if not replace_all and count > 1:
                return (f"❌ old_string appeared {count} times in the file!"
                        f"Use replace_all=true to replace all, or provide more specific context.\n"
                        f"Match text preview: {old_str[:100]}")
            content = content.replace(old_str, new_str) if replace_all else content.replace(old_str, new_str, 1)
            total_replaced += count if replace_all else 1

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        detail = f"{len(patch_list)} groups, {total_replaced} occurrences" if patches else f"{total_replaced} occurrences"
        return f"✅ Replacement successful ({detail})"

    # ── run_shell ──

    def h_run_shell(self, args: dict) -> str:
        from pi_agent._tools_impl import run_shell
        cmd = args["command"]

        if "MEMORY.md" in cmd and any(op in cmd for op in ("rm ", "> ", "truncate", "/dev/null")):
            return "🛡️ Deleting/clearing MEMORY.md is forbidden!"

        # Auto-correct common path mistakes
        for wrong in ["/home/user/workspace", "/home/user/", "~/workspace"]:
            cmd = cmd.replace(wrong + "/", "").replace("cd " + wrong + " && ", "").replace(wrong, "")
        if re.search(r'\bcd\s+workspace/?\s*&&', cmd):
            cmd = re.sub(r'cd\s+workspace/?\s*&&\s*', '', cmd)

        result = run_shell(cmd, timeout=3600,
                          env_vars={"AGENT_BUDGET_REMAINING": "-1"})
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()

        out = ""
        if stdout and stderr:
            out += f"[stdout]\n{stdout}\n\n[stderr]\n{stderr}"
        else:
            out += stdout or stderr or "(no output)"
        return out

    # ── start_shell ──

    def h_start_shell(self, args: dict) -> str:
        from pi_agent._tools_impl import start_shell
        command = args.get("command", "")
        timeout = args.get("timeout", 3600)
        result = start_shell(command, timeout=timeout)
        if result.get("success"):
            return (f"Process {result['pid']} started (status: {result['status']})\n"
                    f"Command: {result['command']}\n"
                    f"Hint: use check_shell({result['pid']}) to monitor output")
        return f"Start failed: {result.get('error', 'unknown')}"

    # ── check_shell ──

    def h_check_shell(self, args: dict) -> str:
        from pi_agent._tools_impl import check_shell
        pid = args.get("pid", -1)
        result = check_shell(pid)
        if not result.get("success"):
            return (
                f"check_shell failed: {result.get('error', 'unknown')}\n\n"
                f"⚠️ This process no longer exists! Do NOT check_shell({pid}) again."
                f"Please do something else: check output directories, read logs to analyze errors,"
                f"fix code and start_shell to retrain, or move on to other experiments."
            )
        out = f"Process {pid}: {result['status']} | Elapsed {result['elapsed']}s"
        if result['status'] == 'loading':
            out += "\n(Data loading phase; no output is normal, please wait patiently, do NOT kill)"
        if result.get("return_code") is not None:
            out += f" | return_code={result['return_code']}"
        if result.get("warning"):
            out += f"\n⚠️ {result['warning']}"
        if result.get("new_output"):
            limit = 4000 if result['status'] in ('error', 'completed') else 2000
            output_text = result['new_output']
            if len(output_text) > limit:
                half = limit // 2
                output_text = output_text[:half] + f"\n... [{len(output_text) - limit} chars omitted] ...\n" + output_text[-half:]
            out += f"\n--- New output ---\n{output_text}"
        if result.get("stderr"):
            limit = 3000 if result['status'] in ('error', 'completed') else 1000
            err_text = result['stderr']
            if len(err_text) > limit:
                err_text = err_text[-limit:]
            out += f"\n--- stderr ---\n{err_text}"
        return out

    # ── kill_shell ──

    def h_kill_shell(self, args: dict) -> str:
        from pi_agent._tools_impl import kill_shell
        pid = args.get("pid", -1)
        result = kill_shell(pid)
        if result.get("success"):
            out = f"Process {pid} terminated | Ran {result['elapsed']}s"
            if result.get("final_stderr"):
                out += f"\n--- Final stderr ---\n{result['final_stderr'][-2000:]}"
            return out
        return f"Termination failed: {result.get('error', 'unknown')}"

    # ── stop ──

    def h_stop(self, args: dict) -> str:
        if self._on_stop:
            self._on_stop()
        memory_files = list(self.memory_dir.glob("survey-*.md"))
        msg = f"Stop signal received. {len(memory_files)} memory files recorded."
        return msg + " Finalizing..."

    # ── Route A: Discovery Tools ──

    def _safe_hypothesis(self, data: dict):
        """安全构造 DiscoveryHypothesis，自动补全缺失字段。"""
        from literature_agent.discovery import DiscoveryHypothesis
        return DiscoveryHypothesis(**{k: v for k, v in data.items()
                                      if k in DiscoveryHypothesis.__dataclass_fields__})

    def h_generate_hypotheses(self, args: dict) -> str:
        """LLM 从 Gap 报告中生成构效关系假设。"""
        from pathlib import Path as _Path
        import json as _json

        # 读取 Gap 报告
        gap_path = self.survey_state.get("gap_report_path",
                                          "workspace/outputs/literature_survey/gap_report.md")
        if not _Path(gap_path).exists():
            gap_path = "workspace/outputs/literature_survey/gap_report.md"
        if not _Path(gap_path).exists():
            return "❌ No gap report found. Run analyze_gaps first."

        gap_text = _Path(gap_path).read_text(encoding="utf-8")
        if len(gap_text) > 15000:
            gap_text = gap_text[:15000] + "\n...[truncated]"

        # 读取论文摘要（提取材料名和性质名）
        summary_path = self.survey_state.get("paper_summary_path",
            "workspace/outputs/literature_survey/paper_summaries.md")
        paper_context = ""
        if _Path(summary_path).exists():
            paper_text = _Path(summary_path).read_text(encoding="utf-8")
            paper_context = paper_text[:10000] if len(paper_text) > 10000 else paper_text

        # LLM 生成假设
        hypo_prompt = (
            "You are a materials scientist. 所有输出必须使用中文。"
            "Based on the research gaps and paper summaries below, "
            "generate 3-5 TESTABLE structure-property relationship hypotheses.\n\n"
            "For each hypothesis output a JSON object with:\n"
            '- id: "hypo_N"\n'
            '- title: short scientific title\n'
            '- description: detailed explanation\n'
            '- materials: [list of material names]\n'
            '- property: target property name\n'
            '- expected_relationship: what you expect to find and why\n'
            '- confidence: 0.0-1.0\n'
            '- novelty_score: 0.0-1.0\n'
            '- validation_status: "pending"\n'
            '- source_gap_id: gap id from the gap report this hypothesis addresses, e.g. "Gap 1"\n'
            '- evidence_chain: [list of paper IDs (p#) from paper summaries supporting this hypothesis]\n'
            '- search_method: "bayesian"\n\n'
            "Return ONLY valid JSON: {\"hypotheses\": [...]}\n\n"
            f"=== RESEARCH GAPS ===\n\n{gap_text}\n\n"
            f"=== PAPER CONTEXT ===\n\n{paper_context}"
        )

        try:
            from utils.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
            from openai import OpenAI
            import re as _re2
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "user", "content": hypo_prompt}],
                max_tokens=8192, temperature=0.2,
            )
            content = resp.choices[0].message.content or ""
            # 提取 JSON
            json_text = content.strip()
            m = _re2.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
            if m: json_text = m.group(1).strip()
            if not json_text.startswith('{'):
                s = json_text.find('{'); e = json_text.rfind('}')
                if s >= 0 and e > s: json_text = json_text[s:e+1]
            data = _json.loads(json_text)
            hypotheses = data.get("hypotheses", [])
        except Exception as e:
            # 兜底：返回最小假设集
            self._print(f"  ⚠️ LLM hypothesis gen failed: {e}, using fallback")
            hypotheses = [
                {"id":"hypo_0","title":"Material-property relationship discovery",
                 "description":"Based on the gap analysis","materials":[],"property":"",
                 "expected_relationship":"To be determined","confidence":0.3,
                 "novelty_score":0.5,"validation_status":"pending","search_method":"bayesian",
                 "source_gap_id":"","evidence_chain":[]}
            ]

        # 保存
        out_dir = _Path("workspace/outputs/literature_survey/discovery")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "hypotheses.json").write_text(
            _json.dumps(hypotheses, ensure_ascii=False, indent=2)
        )
        self.survey_state["hypotheses"] = hypotheses

        return (
            f"✅ Generated {len(hypotheses)} hypotheses\n\n" +
            "\n".join(
                f"{i+1}. [{h.get('validation_status','pending')}] **{h.get('title','')[:100]}**\n"
                f"   Confidence: {h.get('confidence',0):.2f} | Novelty: {h.get('novelty_score',0):.2f}"
                for i, h in enumerate(hypotheses[:10])
            ) +
            f"\n\nSaved to workspace/outputs/literature_survey/discovery/hypotheses.json\n"
            f"Next: run_discovery_search(hypothesis_index=N) to explore each hypothesis."
        )

    # ── 文献证据索引：基于 Agent 自写的知识图谱（Markdown）打分 ──

    _PROPERTY_KEYWORD_MAP = {
        "选择性": ["selectivity", "separation factor"],
        "容量": ["capacity", "uptake", "loading"],
        "吸附": ["adsorption", "uptake", "capture"],
        "焓": ["isosteric heat", "qst", "enthalpy"],
        "再生": ["regeneration", "working capacity", "energy"],
        "稳定性": ["stability", "degradation", "cyclability"],
        "扩散": ["diffusion", "kinetics"],
        "催化": ["catalysis", "tof", "conversion", "activity"],
        "效率": ["efficiency"],
        "能耗": ["energy penalty", "regeneration energy"],
        "循环": ["cyclability", "cycle"],
    }
    _VALUE_UNIT_RE = re.compile(
        r'(\d+(?:\.\d+)?)\s*(mmol/g|mol/kg|mmol/cm3|mg/g|kJ/mol|wt%|m2/g|bar|K|%|h|min|eV)',
        re.IGNORECASE,
    )

    def _load_knowledge_source(self) -> Optional[str]:
        """读取 Agent 自写的知识图谱 Markdown；不存在则回退论文摘要。"""
        from pathlib import Path as _Path
        for cand in (
            "workspace/outputs/literature_survey/knowledge_graph.md",
            self.survey_state.get(
                "paper_summary_path",
                "workspace/outputs/literature_survey/paper_summaries.md",
            ),
        ):
            if _Path(cand).exists():
                try:
                    return _Path(cand).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
        return None

    def _load_evidence_source(self) -> Optional[str]:
        """证据源 = 知识图谱/摘要 + 全文缓存（workspace/data/papers/*.md）。"""
        from pathlib import Path as _Path
        base = self._load_knowledge_source() or ""
        parts = [base] if base.strip() else []
        papers_dir = _Path("workspace/data/papers")
        if papers_dir.exists():
            total = sum(len(p) for p in parts)
            for md in sorted(papers_dir.glob("*.md")):
                try:
                    txt = md.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if total + len(txt) > 300_000:
                    parts.append(f"\n\n<!-- 全文缓存过多，已截断：{md.name} -->\n")
                    break
                parts.append(txt)
                total += len(txt)
        return "\n\n".join(parts) if parts else None

    def h_get_full_text(self, args: dict) -> str:
        """获取论文全文：Sciverse 全文片段 / PDF 下载解析 / 缓存摘要。"""
        from pathlib import Path as _Path
        import json as _json
        import re as _re

        paper_id = (args.get("paper_id") or "").strip()
        if not paper_id:
            return "❌ get_full_text 需要 paper_id 参数（如 p1、DOI 或标题关键词）。"

        papers_dir = _Path("workspace/data/literature_cache")
        results_file = papers_dir / "search_results.json"
        papers_file = papers_dir / "papers.json"

        meta = None
        cached_text = None

        # 1) papers.json：键即 paper_id
        if papers_file.exists():
            try:
                papers = _json.loads(papers_file.read_text(encoding="utf-8"))
                if isinstance(papers, dict) and paper_id in papers:
                    raw = papers[paper_id]
                    if isinstance(raw, dict):
                        cached_text = (
                            f"{raw.get('title', '')}\n\n{raw.get('abstract', '')}"
                        ).strip()
                    else:
                        cached_text = str(raw)
            except Exception:
                pass

        # 2) search_results.json：id / DOI / 标题匹配
        if meta is None and results_file.exists():
            try:
                results = _json.loads(results_file.read_text(encoding="utf-8"))
            except Exception:
                results = []
            pid_l = paper_id.lower()
            for r in results:
                rid = str(r.get("id", "")).lower()
                doi = str(r.get("doi", "") or "").lower()
                title = str(r.get("title", "") or "").lower()
                if (rid == pid_l or (doi and (doi == pid_l or doi.endswith(pid_l)))
                        or (len(pid_l) >= 4 and title and pid_l in title)):
                    meta = r
                    break
        if meta is None:
            for r in (self.survey_state.get("search_results") or []):
                rid = str(r.get("id", "")).lower()
                doi = str(r.get("doi", "") or "").lower()
                title = str(r.get("title", "") or "").lower()
                if (rid == paper_id.lower() or doi.lower() == paper_id.lower()
                        or (len(paper_id) >= 4 and paper_id.lower() in title)):
                    meta = r
                    break

        if meta is None and cached_text is None:
            return (
                "❌ 找不到该论文的元数据。请先 search_papers，"
                "或检查 paper_id（p1/p2… 对应 papers.json 的键，或 DOI/标题关键词）。"
            )

        # 提取可用的标题（用于 arXiv 回退）
        fallback_title = None
        if meta:
            fallback_title = meta.get("title")
        elif cached_text:
            first = next(
                (ln.strip() for ln in cached_text.splitlines() if ln.strip()), ""
            )
            fallback_title = re.sub(
                r'^(title|标题)[:\s]+', '', first, flags=re.IGNORECASE,
            )

        out_dir = _Path("workspace/data/papers")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = _re.sub(r'[^\w\-.]+', '_', paper_id)[:80] or "paper"
        md_path = out_dir / f"{safe}.md"

        # 3) 全文缓存
        if md_path.exists():
            text = md_path.read_text(encoding="utf-8", errors="replace")
            shown = text[:40000]
            return (
                f"✅ 命中全文缓存：{md_path}（{len(text)} 字符）\n\n{shown}"
                + ("\n…[截断]" if len(text) > 40000 else "")
            )

        # 4) 获取全文
        text = ""
        source = "cached_text"
        if meta:
            doc_id = None
            raw = meta.get("raw_metadata") or {}
            if isinstance(raw, dict):
                doc_id = raw.get("doc_id") or raw.get("id")
            if meta.get("source") == "sciverse" or doc_id:
                try:
                    from literature_agent.search import SciverseSearcher
                    searcher = SciverseSearcher(api_key=os.environ.get("SCIVERSE_API_KEY", ""))
                    snippet = searcher.read_content(doc_id, offset=0, limit=16384) if doc_id else None
                    if snippet:
                        text = f"# {meta.get('title', paper_id)}\n\n## 全文片段（Sciverse）\n\n{snippet}"
                        source = "sciverse_fulltext"
                except Exception:
                    pass
            if not text and meta.get("pdf_url"):
                try:
                    pdf_path = out_dir / f"{safe}.pdf"
                    txt = self._download_and_parse_pdf(meta["pdf_url"], pdf_path)
                    if txt:
                        text = txt
                        source = "pdf:markitdown"
                except Exception as e:
                    self._print(f"  ⚠️ PDF 获取/解析失败: {e}")
        if not text and fallback_title:
            # 无可用链接（含无元数据、仅缓存摘要）→ 按标题去 arXiv 找 PDF
            try:
                pdf_url = self._arxiv_pdf_by_title(fallback_title)
                if pdf_url:
                    pdf_path = out_dir / f"{safe}.pdf"
                    txt = self._download_and_parse_pdf(pdf_url, pdf_path)
                    if txt:
                        text = txt
                        source = "pdf:markitdown (arxiv-fallback)"
            except Exception as e:
                self._print(f"  ⚠️ arXiv 回退失败: {e}")
        if not text and cached_text:
            text = f"# {paper_id}（缓存摘要）\n\n{cached_text}"
            source = "cached_abstract"

        if not text.strip():
            return (
                "❌ 未能获取全文。该论文可能没有可用的 pdf_url 或 Sciverse 全文；"
                "可用来源：{0}".format(meta.get("source", "unknown") if meta else "papers.json 缓存")
            )

        md_path.write_text(text, encoding="utf-8")
        self.survey_state.setdefault("parsed_papers", {})[paper_id] = {
            "path": str(md_path), "source": source,
        }
        shown = text[:40000]
        return (
            f"✅ 全文已获取（{source}，{len(text)} 字符）→ {md_path}\n\n{shown}"
            + ("\n…[截断，全文已存文件，可 read_file 查看]" if len(text) > 40000 else "")
        )

    def _download_and_parse_pdf(self, url: str, pdf_path: Path) -> Optional[str]:
        """下载 PDF 并用 MarkItDown 解析为全文 Markdown。"""
        import requests as _requests
        resp = _requests.get(
            url, headers={"User-Agent": "goai-pi-agent/1.0"}, timeout=60,
        )
        if resp.status_code != 200 or resp.content[:4] != b"%PDF":
            return None
        pdf_path.write_bytes(resp.content)
        from literature_agent.parser import DocumentParser
        doc = DocumentParser().parse(str(pdf_path))
        return doc.full_text or f"# {doc.title}\n\n{doc.abstract}"

    def _arxiv_pdf_by_title(self, title: str) -> Optional[str]:
        """按标题在 arXiv 检索，返回最相似条目的 PDF 链接（找不到返回 None）。"""
        from urllib.parse import quote
        import xml.etree.ElementTree as _ET
        from difflib import SequenceMatcher
        import requests as _requests

        q = quote(f'ti:"{title}"')
        try:
            resp = _requests.get(
                f"http://export.arxiv.org/api/query?search_query={q}&max_results=5",
                headers={"User-Agent": "goai-pi-agent/1.0"},
                timeout=45,
            )
            if resp.status_code != 200:
                return None
            ns = {"a": "http://www.w3.org/2005/Atom"}
            root = _ET.fromstring(resp.text)
            best, best_ratio = None, 0.0
            for entry in root.findall("a:entry", ns):
                et = entry.find("a:title", ns)
                pdf = entry.find("a:link[@title='pdf']", ns)
                if et is None or pdf is None:
                    continue
                cand = (et.text or "").strip()
                ratio = SequenceMatcher(None, title.lower(), cand.lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best = pdf.attrib.get("href")
            return best if best and best_ratio >= 0.55 else None
        except Exception:
            return None

    def _property_keywords(self, property_name: str) -> List[str]:
        """把假设性质名（中英混排）映射为文献检索关键词。"""
        kws: set = set()
        text = (property_name or "").lower()
        for zh, en_list in self._PROPERTY_KEYWORD_MAP.items():
            if zh in text:
                kws.update(en_list)
        for tok in re.findall(r'[a-z][a-z0-9\-]{1,20}', text):
            if len(tok) >= 2:
                kws.add(tok)
        return sorted(kws) or ["adsorption", "capacity", "selectivity"]

    # 性质类型 → 数值单位（按类型分桶，避免容量/热/比表面积混池）
    _PROPERTY_UNIT_BUCKETS = (
        (("mmol/g", "mol/kg", "mmol/cm3", "mg/g", "wt%"),
         ("容量", "capacity", "uptake", "loading", "吸附", "capture", "adsorption")),
        (("kj/mol",),
         ("焓", "qst", "enthalpy", "等量吸附热", "吸附热")),
        (("m2/g",),
         ("bet", "surface area", "比表面积", "表面积")),
        (("bar",),
         ("压力", "pressure")),
        (("k",),
         ("温度", "temperature")),
        (("%", "wt%"),
         ("效率", "efficiency")),
    )

    def _unit_filter(self, property_name: str):
        """根据性质名返回应收集的数值单位集合（None = 不过滤）。"""
        text = (property_name or "").lower()
        matched = set()
        for units, kws in self._PROPERTY_UNIT_BUCKETS:
            if any(k in text for k in kws):
                matched.update(units)
        return matched or None

    def _build_evidence_index(self, source_text: str, hyp) -> Dict:
        """从文献文本构建证据索引：块切分 + 材料 token + 性质关键词 + 文献数值。"""
        blocks = [b.strip() for b in re.split(r'\n(?=#{1,3} )', source_text) if len(b.strip()) > 60]
        if not blocks:
            blocks = [source_text]

        material_tokens: set = set()
        for m in (hyp.materials or []):
            for part in re.split(r'[/\s,，、]+', m):
                part = part.strip()
                if len(part) >= 3 and not part.isdigit():
                    material_tokens.add(part.lower())
        # 补充文献中的材料名（化学式/MOF 家族），严格正则避免误匹配普通英文词
        material_tokens.update(
            m.lower() for m in re.findall(
                r'\b(?:[A-Z][a-z]?\d+[A-Za-z0-9]*(?:-[A-Za-z0-9]+)*|ZIF-\d+|UiO-\d+|MIL-\d+|HKUST-\d+|IRMOF-\d+|MOF-\d+)\b',
                source_text,
            )
        )

        prop_kws = self._property_keywords(hyp.property)
        unit_filter = self._unit_filter(hyp.property)
        values: List[float] = []
        for block in blocks:
            lower = block.lower()
            for kw in prop_kws:
                for m in re.finditer(re.escape(kw), lower):
                    window = lower[max(0, m.start() - 120): m.end() + 160]
                    for vm in self._VALUE_UNIT_RE.finditer(window):
                        unit = (vm.group(2) or "").lower()
                        if unit_filter is not None and unit not in unit_filter:
                            continue
                        v = float(vm.group(1))
                        if 0 < v < 1e6:
                            values.append(v)
        values = sorted(set(round(v, 4) for v in values))[:500]

        return {
            "blocks": blocks,
            "material_tokens": sorted(material_tokens),
            "prop_keywords": prop_kws,
            "values": values,
        }

    def _search_space(self, evid: Dict) -> Dict[str, Tuple[float, float]]:
        """根据文献数值范围定义贝叶斯搜索空间（IQR 稳健区间，抵抗离群值）。"""
        values = sorted(evid.get("values") or [])
        if values:
            n = len(values)
            q1 = values[max(0, n // 4)]
            q3 = values[min(n - 1, 3 * n // 4)]
            median = values[n // 2]
            iqr = max(q3 - q1, 1e-9)
            # Tukey 围栏：落在 1.5×IQR 之外视为离群值，不进入搜索区间
            lo = max(0.001, q1 - 1.5 * iqr)
            hi = q3 + 1.5 * iqr
            # 文献值高度集中（IQR≈0）时按中位数比例兜底，保证可搜索空间
            lo = min(lo, median * 0.5)
            hi = max(hi, median * 2.0)
        else:
            lo, hi = 0.1, 100.0
        return {
            "property_value": (float(lo), float(hi)),
            "composition_x": (0.0, 1.0),
            "temperature": (300.0, 1500.0),
        }

    def _evidence_score(self, params: Dict, hyp, evid: Dict) -> float:
        """文献证据打分：材料覆盖率 + 材料×性质共现 + 数值接近文献报告值。"""
        blocks = evid["blocks"]
        total = len(blocks)
        if total == 0:
            return 0.3

        cand_mats = params.get("materials") or params.get("material") or (hyp.materials or [])
        if isinstance(cand_mats, str):
            cand_mats = [cand_mats]
        cand_mats = [str(m).lower() for m in cand_mats]
        mats = evid["material_tokens"]
        kws = evid["prop_keywords"]
        values = evid["values"]

        # 优先按假设材料匹配；无命中时放宽到通用材料 token
        if cand_mats:
            mat_blocks = [b for b in blocks if any(m in b.lower() for m in cand_mats)]
            if not mat_blocks:
                mat_blocks = [b for b in blocks if any(t in b.lower() for t in mats)]
        else:
            mat_blocks = [b for b in blocks if any(t in b.lower() for t in mats)]

        score = 0.3
        if mat_blocks:
            score += 0.20 * len(mat_blocks) / total
            co = sum(1 for b in mat_blocks if any(k in b.lower() for k in kws))
            score += 0.20 * co / max(len(mat_blocks), 1)
            cv = params.get("property_value") or params.get("value") or 0
            if values and cv:
                # top-3 最近文献值的平均相似度：落在文献值密集区才高分，孤点命中不再满分
                sims = sorted(1.0 / (1.0 + abs(cv - v) / max(v, 1e-6)) for v in values)
                best = sum(sims[-3:]) / max(len(sims[-3:]), 1)
                score += 0.30 * best
        return min(score, 1.0)

    def h_run_discovery_search(self, args: dict) -> str:
        """执行搜索算法探索材料-性质空间。

        评分基于 Agent 自写的知识图谱（knowledge_graph.md，Markdown）或论文摘要：
        材料覆盖率 + 材料×性质共现 + 数值接近文献报告值，不再依赖 JSON 知识图谱。
        """
        from literature_agent.discovery import DiscoveryEngine
        from pathlib import Path as _Path
        import json as _json

        idx = args.get("hypothesis_index", 0)
        n_iterations = min(args.get("n_iterations", 30), 100)
        method = args.get("search_method", "bayesian")

        hypotheses_data = self.survey_state.get("hypotheses", [])
        if not hypotheses_data:
            hypo_file = _Path("workspace/outputs/literature_survey/discovery/hypotheses.json")
            if hypo_file.exists():
                hypotheses_data = _json.loads(hypo_file.read_text())
                self.survey_state["hypotheses"] = hypotheses_data
            else:
                return "❌ No hypotheses found. Run generate_hypotheses first."

        if idx >= len(hypotheses_data):
            return f"❌ Invalid hypothesis_index: {idx} (only {len(hypotheses_data)} hypotheses available)"

        from literature_agent.discovery import DiscoveryHypothesis
        hyp = self._safe_hypothesis(hypotheses_data[idx])

        # ── 知识来源：优先 Agent 自写的知识图谱（Markdown），缺省回退论文摘要 ──
        kg_md = "workspace/outputs/literature_survey/knowledge_graph.md"
        source_text = self._load_evidence_source()
        if not source_text:
            return (
                "❌ 找不到知识来源（knowledge_graph.md / paper_summaries.md / data/papers/*.md）。\n"
                f"请先 extract_knowledge 整理论文摘要，再 write_file 自己的知识图谱 "
                f"{kg_md}（材料/性质/数值/关系，Markdown 格式），然后重试。"
            )

        evid = self._build_evidence_index(source_text, hyp)

        engine = self.survey_state.get("discovery_engine")
        if engine is None:
            engine = DiscoveryEngine()
            self.survey_state["discovery_engine"] = engine
        # LLM × 搜索融合：让 LLM 评估中间候选合理性并引导剪枝（路线 A 核心评分点）
        from literature_agent.discovery import BayesianOptimizer, MCTSSearcher
        engine.bayes_opt = BayesianOptimizer(llm_guide=self._llm_guide_candidates)
        engine.mcts_searcher = MCTSSearcher(llm_guide=self._llm_guide_node)

        # Run search
        out_dir = _Path("workspace/outputs/literature_survey/discovery")
        out_dir.mkdir(parents=True, exist_ok=True)

        search_results = {
            "hypothesis_index": idx,
            "search_method": method,
            "iterations": n_iterations,
            "evidence": {
                "source": (
                    "knowledge_graph.md + paper_summaries.md + papers/*.md"
                    if _Path(kg_md).exists() else "paper_summaries.md"
                ),
                "blocks": len(evid["blocks"]),
                "material_tokens": len(evid["material_tokens"]),
                "property_keywords": evid["prop_keywords"][:10],
                "literature_values": evid["values"][:20],
            },
            "llm_guidance": True,
            "llm_guidance_calls": getattr(self, "_llm_guide_calls", 0),
        }

        if method in ("bayesian", "hybrid"):
            param_space = self._search_space(evid)
            best_params, best_score, log = engine.bayes_opt.optimize(
                hyp, param_space,
                objective_fn=lambda p: self._evidence_score(p, hyp, evid),
                n_iterations=n_iterations,
            )
            search_results.update({
                "best_params": best_params, "best_score": best_score,
                "iteration_log": log[-10:],
            })
            hyp.confidence = max(hyp.confidence, best_score)
            hyp.candidates_explored = len(log) + 10
            hyp.search_iterations = n_iterations

        elif method == "mcts":
            root_state = {"materials": hyp.materials, "property": hyp.property}
            best_state, best_score, log = engine.mcts_searcher.search(
                root_state,
                expand_fn=lambda s: [{"material": m, "value": v}
                                     for m in hyp.materials[:3]
                                     for v in [0.5, 1.0, 1.5, 2.0, 3.0]],
                simulate_fn=lambda s: self._evidence_score(s, hyp, evid),
                n_iterations=n_iterations * 5,
            )
            search_results.update({
                "best_state": best_state, "best_score": best_score,
                "search_log": log,
            })
            hyp.confidence = max(hyp.confidence, best_score)
            hyp.candidates_explored = len(log) * 5
            hyp.search_iterations = n_iterations * 5

        # 搜索完成后的 LLM 引导实际调用次数
        search_results["llm_guidance_calls"] = getattr(self, "_llm_guide_calls", 0)

        # 写回搜索状态到 hypotheses.json（供 generate_discovery_report 汇总）
        hypotheses_data[idx] = asdict(hyp)
        (out_dir / "hypotheses.json").write_text(
            _json.dumps(hypotheses_data, ensure_ascii=False, indent=2))
        self.survey_state["hypotheses"] = hypotheses_data

        # Save search results
        (out_dir / f"search_h{idx}.json").write_text(
            _json.dumps(search_results, ensure_ascii=False, indent=2)
        )
        self.survey_state["search_results"] = search_results

        return (
            f"✅ Discovery search complete for hypothesis #{idx}: '{hyp.title[:80]}'\n"
            f"   Search method: {method}\n"
            f"   Iterations: {n_iterations} | Candidates explored: {hyp.candidates_explored}\n"
            f"   Best score: {best_score:.3f}\n"
            f"   Evidence: {len(evid['blocks'])} blocks, {len(evid['material_tokens'])} materials, "
            f"{len(evid['values'])} literature values\n"
            f"   LLM 引导：已启用（{getattr(self, '_llm_guide_calls', 0)} 次中间评估）\n"
            f"   Updated confidence: {hyp.confidence:.2f}\n\n"
            f"Next: validate_discovery(hypothesis_index={idx} 或 'all') 完成双轨验证。"
        )

    def _apply_validation(self, hyp) -> tuple:
        """对单条假设执行双轨验证，更新状态，返回 (hyp, result)。"""
        from literature_agent.discovery import MaterialsProjectValidator
        validator = MaterialsProjectValidator()
        result = validator.validate(hyp)
        vs = result.get("validation_source", "none")
        if result.get("overall_match"):
            hyp.validation_status = (
                "validated" if vs == "database" else "literature_supported"
            )
        elif result.get("databases_checked") or result.get("validation_notes"):
            hyp.validation_status = "inconclusive"
        else:
            hyp.validation_status = "pending"
        hyp.external_validation = result
        return hyp, result

    def h_validate_discovery(self, args: dict) -> str:
        """对假设进行外部数据库/文献证据链交叉验证（统一走本工具）。"""
        from literature_agent.discovery import DiscoveryEngine, MaterialsProjectValidator
        from literature_agent.discovery import DiscoveryHypothesis
        from pathlib import Path as _Path
        import json as _json

        idx = args.get("hypothesis_index", 0)
        hypotheses_data = self.survey_state.get("hypotheses", [])
        if not hypotheses_data:
            hypo_file = _Path("workspace/outputs/literature_survey/discovery/hypotheses.json")
            if hypo_file.exists():
                hypotheses_data = _json.loads(hypo_file.read_text())
            else:
                return "❌ No hypotheses found."

        out_dir = _Path("workspace/outputs/literature_survey/discovery")
        out_dir.mkdir(parents=True, exist_ok=True)

        # ── 批量验证（hypothesis_index="all" 或缺省）──
        if str(idx).lower() in ("all", ""):
            summary = ["✅ 批量验证完成（validate_discovery all）：", ""]
            for i, hd in enumerate(hypotheses_data):
                hyp = self._safe_hypothesis(hd)
                hyp, result = self._apply_validation(hyp)
                hypotheses_data[i] = asdict(hyp)
                status_icon = {
                    "validated": "✅", "literature_supported": "📚",
                    "inconclusive": "❓", "pending": "⏳",
                }.get(hyp.validation_status, "❓")
                summary.append(
                    f"   {status_icon} hyp[{i}] → {hyp.validation_status}"
                    f"（conf={hyp.confidence:.2f}）{hyp.title[:50]}"
                )
            (out_dir / "hypotheses.json").write_text(
                _json.dumps(hypotheses_data, ensure_ascii=False, indent=2)
            )
            self.survey_state["hypotheses"] = hypotheses_data
            summary.append(
                "\n全部假设的 validation_status / external_validation 已写入 "
                "hypotheses.json（可审计验证记录）。\n"
                "Next: generate_discovery_report 汇总最新验证结果。"
            )
            return "\n".join(summary)

        # ── 单条验证 ──
        if isinstance(idx, int) and 0 <= idx < len(hypotheses_data) or (
            str(idx).isdigit() and 0 <= int(idx) < len(hypotheses_data)
        ):
            idx = int(idx)
        else:
            return f"❌ Invalid hypothesis_index: {idx}（可用 0-{len(hypotheses_data)-1} 或 'all'）"

        hyp = self._safe_hypothesis(hypotheses_data[idx])
        hyp, result = self._apply_validation(hyp)

        # Save updated hypothesis
        hypotheses_data[idx] = asdict(hyp)
        (out_dir / "hypotheses.json").write_text(
            _json.dumps(hypotheses_data, ensure_ascii=False, indent=2)
        )
        self.survey_state["hypotheses"] = hypotheses_data

        evidence = result.get("supporting_evidence", [])
        notes = result.get("validation_notes", [])
        return (
            f"{'✅' if result.get('overall_match') else '❓'} Validation for hypothesis #{idx}: '{hyp.title[:80]}'\n"
            f"   Status: {hyp.validation_status}\n"
            f"   Databases checked: {result.get('databases_checked', [])}\n"
            f"   Materials Project hits: {result.get('details', {}).get('materials_project', {}).get('matching_entries', [])}\n"
            f"   Supporting evidence ({len(evidence)} entries):\n" +
            "\n".join(f"   - {e}" for e in evidence[:5]) +
            (f"\n   Notes: " + "; ".join(notes) if notes else "") +
            f"\n\nNext: generate_discovery_report to produce the final Route A report."
        )

    # ── LLM × 搜索融合：中间候选的科学合理性评估与剪枝引导 ──

    def _llm_text(self, prompt: str, max_tokens: int = 1000) -> str:
        """调用 DeepSeek 返回纯文本；失败返回空串，保证搜索流程不中断。"""
        try:
            from utils.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
            from openai import OpenAI
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=0.1,
            )
            msg = resp.choices[0].message
            return (
                (msg.content or "").strip()
                or (getattr(msg, "reasoning_content", "") or "").strip()
            )
        except Exception:
            return ""

    def _llm_guide_candidates(self, candidates: list) -> list:
        """LLM 评估一组中间候选参数（贝叶斯优化），返回带 score 的副本。"""
        self._llm_guide_calls = getattr(self, "_llm_guide_calls", 0) + 1
        if not candidates:
            return candidates
        import json as _json
        try:
            prompt = (
                "你是材料科学评审。以下是一组构效关系搜索的中间候选参数"
                "（性质数值/组成比例/温度等）。请评估每个候选的科学合理性，打分 0-1：\n"
                "1=完全合理（落在文献常见范围），0=明显不合理（如温度远超物理上限、"
                "组成超出合理掺杂范围）。\n"
                '只返回 JSON：{"scores": [0.8, 0.3, ...]}，顺序与输入一致，不要输出其他内容。\n\n'
                "候选列表：\n" + _json.dumps(candidates, ensure_ascii=False)[:3000]
            )
            reply = self._llm_text(prompt, max_tokens=600)
            m = re.search(r'\{[\s\S]*\}', reply)
            if not m:
                return candidates
            data = _json.loads(m.group(0))
            scores = data.get("scores") or []
            out = []
            for i, c in enumerate(candidates):
                s = scores[i] if i < len(scores) else None
                item = dict(c)
                if isinstance(s, (int, float)) and 0 <= s <= 1:
                    item["score"] = float(s)
                out.append(item)
            return out
        except Exception:
            return candidates

    def _llm_guide_node(self, node_state: dict):
        """LLM 评估 MCTS 节点状态是否科学合理，返回 (is_promising, adjustment)。"""
        self._llm_guide_calls = getattr(self, "_llm_guide_calls", 0) + 1
        import json as _json
        try:
            prompt = (
                "你是材料科学评审。以下是一个材料构效关系搜索的节点状态。"
                "判断该方向是否值得继续探索。\n"
                '只返回 JSON：{"is_promising": true/false, "adjustment": 0.0}，'
                "adjustment 为 -0.3~0.3 的合理度修正。不要输出其他内容。\n\n"
                "节点状态：\n" + _json.dumps(node_state, ensure_ascii=False)[:1500]
            )
            reply = self._llm_text(prompt, max_tokens=300)
            m = re.search(r'\{[\s\S]*\}', reply)
            if not m:
                return True, 0.0
            data = _json.loads(m.group(0))
            promising = bool(data.get("is_promising", True))
            adj = data.get("adjustment", 0.0)
            if not isinstance(adj, (int, float)):
                adj = 0.0
            return promising, float(max(-0.3, min(0.3, adj)))
        except Exception:
            return True, 0.0

    def h_generate_discovery_report(self, args: dict) -> str:
        """生成路线 A 发现报告。"""
        from literature_agent.discovery import DiscoveryReport, DiscoveryHypothesis
        from pathlib import Path as _Path
        import json as _json

        hypotheses_data = self.survey_state.get("hypotheses", [])
        if not hypotheses_data:
            hypo_file = _Path("workspace/outputs/literature_survey/discovery/hypotheses.json")
            if hypo_file.exists():
                hypotheses_data = _json.loads(hypo_file.read_text())

        if not hypotheses_data:
            return "❌ No hypotheses found. Run generate_hypotheses first."

        hypotheses = [self._safe_hypothesis(h) for h in hypotheses_data]

        report = DiscoveryReport(
            title=f"Structure-Property Relationship Discovery",
            hypotheses=hypotheses,
            total_candidates=len(hypotheses),
            total_explored=sum(h.candidates_explored for h in hypotheses),
            validated_count=sum(1 for h in hypotheses if h.validation_status == "validated"),
            refuted_count=sum(1 for h in hypotheses if h.validation_status == "refuted"),
            materials_project_hits=sum(1 for h in hypotheses
                                      if h.external_validation.get("overall_match")),
            search_summary=f"Explored {len(hypotheses)} hypotheses via Bayesian optimization and MCTS.",
        )

        out_dir = _Path("workspace/outputs/literature_survey/discovery")
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path, json_path = report.save(str(out_dir))

        self.survey_state["discovery_report"] = report.to_dict()

        return (
            f"✅ Discovery report generated\n"
            f"   Markdown: {md_path}\n"
            f"   JSON:     {json_path}\n"
            f"   Hypotheses: {len(hypotheses)}\n"
            f"   Validated: {report.validated_count} | Refuted: {report.refuted_count}\n"
            f"   Materials Project hits: {report.materials_project_hits}"
        )

    # ── Literature Survey Tools ──

    def h_search_papers(self, args: dict) -> str:
        """搜索科学文献。"""
        from literature_agent.search import LiteratureSearcher
        query = args.get("query", "")
        top_k = min(args.get("top_k", 20), 50)
        material = args.get("material")
        prop = args.get("property")

        sciverse_key = os.environ.get("SCIVERSE_API_KEY", "")
        searcher = LiteratureSearcher(
            cache_dir="workspace/data/literature_cache",
            sciverse_api_key=sciverse_key,
        )
        results = searcher.search(query, top_k=top_k, material=material, property_name=prop)

        # 累积保存：与已有结果合并去重，避免后续检索覆盖前次结果
        import json as _json
        from pathlib import Path as _Path
        out_dir = _Path("workspace/data/literature_cache")
        out_dir.mkdir(parents=True, exist_ok=True)

        results_json = [r.to_dict() for r in results]

        # 加载已有结果并合并去重
        existing = []
        cache_file = out_dir / "search_results.json"
        if cache_file.exists():
            try:
                existing = _json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                existing = []

        seen = set()
        merged = []
        for item in existing + results_json:
            key = item.get("doi") or item.get("title", "")
            if key and key not in seen:
                seen.add(key)
                merged.append(item)
        cache_file.write_text(_json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

        # 记录本轮新增唯一论文数（供 assess_search_coverage 计算边际收益）
        new_count = max(0, len(merged) - len(existing))
        try:
            from datetime import datetime as _dt
            log_entry = {
                "timestamp": _dt.now().isoformat(),
                "query": query,
                "result_count": len(results),
                "new_unique": new_count,
                "total_unique": len(merged),
            }
            with open(out_dir / "search_log.jsonl", "a", encoding="utf-8") as _lf:
                _lf.write(_json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

        # Store in session state
        self.survey_state["search_results"] = merged

        # Return readable summary
        summary_lines = [f"Found {len(results)} papers for query: '{query}'", ""]
        for i, r in enumerate(results[:10]):
            summary_lines.append(
                f"{i+1}. **{r.title[:100]}** ({r.year or 'N/A'})"
                f"  \n   Authors: {', '.join(r.authors[:3])}"
                f"  \n   Source: {r.source} | Score: {r.score:.2f}"
                f"  \n   DOI: {r.doi or 'N/A'}"
            )
        if len(results) > 10:
            summary_lines.append(f"\n... and {len(results)-10} more papers")
        summary_lines.append(f"\nResults saved to workspace/data/literature_cache/search_results.json")
        return "\n".join(summary_lines)

    _COVERAGE_STOPWORDS = {
        "the", "and", "for", "with", "from", "that", "this", "these", "those",
        "are", "was", "were", "been", "have", "has", "had", "will", "would",
        "can", "could", "should", "may", "might", "not", "but", "its", "their",
        "our", "his", "her", "into", "onto", "upon", "using", "used", "based",
        "such", "than", "then", "when", "where", "which", "while", "within",
        "through", "between", "about", "after", "before", "during", "also",
        "however", "although", "more", "most", "less", "least", "new", "novel",
        "high", "low", "large", "small", "good", "better", "best", "doi", "vol",
        "pp", "fig", "table", "et", "al", "de", "la", "le", "paper", "study",
        "results", "result", "show", "shows", "shown", "found", "report",
    }

    def _coverage_tokens(self, text: str) -> List[str]:
        toks = re.findall(r'[a-z][a-z0-9-]{2,}', (text or "").lower())
        return [t for t in toks if t not in self._COVERAGE_STOPWORDS]

    def h_assess_search_coverage(self, args: dict) -> str:
        """检索覆盖审计：唯一论文 / 来源 / 年份 / 主题词覆盖 / 边际收益。"""
        from pathlib import Path as _Path
        import json as _json
        from collections import Counter

        cache_dir = _Path("workspace/data/literature_cache")
        results_file = cache_dir / "search_results.json"
        log_file = cache_dir / "search_log.jsonl"

        results = []
        if results_file.exists():
            try:
                results = _json.loads(results_file.read_text(encoding="utf-8"))
            except Exception:
                results = []
        if not results:
            results = self.survey_state.get("search_results") or []

        # 去重（doi / 标题）
        seen, unique = set(), []
        for r in results:
            key = ((r.get("doi") or "") or (r.get("title") or "")).strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(r)

        sources = Counter((r.get("source") or "unknown") for r in unique)
        years = sorted(r.get("year") for r in unique if r.get("year"))

        # 检索日志（含 new_unique 的条目用于边际收益）
        queries = []
        gains = []
        if log_file.exists():
            try:
                for line in log_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    item = _json.loads(line)
                    queries.append(item.get("query", ""))
                    if "new_unique" in item:
                        gains.append((
                            item.get("query", ""),
                            item.get("new_unique", 0),
                            item.get("result_count", 0),
                        ))
            except Exception:
                pass

        # 主题词覆盖：论文高频词 vs 已检索词
        all_terms = Counter()
        for r in unique:
            all_terms.update(self._coverage_tokens(f"{r.get('title', '')} {r.get('abstract') or ''}"))
        query_terms = set()
        for q in queries:
            query_terms.update(self._coverage_tokens(q))
        suggested = [
            t for t, c in all_terms.most_common(300)
            if t not in query_terms and c >= 2
        ][:10]

        recent_gains = gains[-5:] if gains else []
        if recent_gains:
            last_new = recent_gains[-1][1]
            avg_new = sum(g[1] for g in recent_gains) / len(recent_gains)
        else:
            last_new = None
            avg_new = None

        total_returned = sum(g[2] for g in gains) or len(results) or 1
        capture_efficiency = len(unique) / total_returned

        if not queries:
            decision = "先执行至少 1 轮检索（search_papers），再回来评估覆盖。"
        elif last_new is not None and last_new <= 3 and len(unique) >= 15:
            decision = (
                "🔴 最近一轮新增唯一论文过少（≤3），且已累计 ≥15 篇"
                " → 建议停止检索，进入知识整理/Gap 分析。"
            )
        elif capture_efficiency < 0.15 and len(unique) >= 10:
            decision = (
                "🟠 捕获效率偏低（<15%）→ 建议调整检索词角度"
                "（换同义词/子主题/年份范围），再评估。"
            )
        else:
            decision = (
                "🟢 覆盖仍在增长 → 建议继续从不同角度检索 1-2 轮，然后重新评估。"
            )

        report = {
            "unique_papers": len(unique),
            "sources": dict(sources),
            "year_min": years[0] if years else None,
            "year_max": years[-1] if years else None,
            "search_rounds": len(queries),
            "recent_gains": [
                {"query": q, "new_unique": n, "result_count": c}
                for q, n, c in recent_gains
            ],
            "capture_efficiency": round(capture_efficiency, 3),
            "suggested_queries": suggested,
            "decision": decision,
        }
        report_path = cache_dir / "coverage_report.json"
        try:
            report_path.write_text(_json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self.survey_state["coverage_report"] = report

        lines = [
            "✅ 检索覆盖审计完成",
            f"   唯一论文：{len(unique)}",
            f"   来源分布：{', '.join(f'{k}({v})' for k, v in sources.items()) or '无'}",
            f"   年份范围：{years[0] if years else '?'} – {years[-1] if years else '?'}",
            f"   检索轮次：{len(queries)}",
        ]
        if recent_gains:
            lines.append(
                "   最近 5 轮新增唯一论文："
                + ", ".join(f"'{q[:20]}': +{n}" for q, n, c in recent_gains)
            )
        lines.append(f"   捕获效率：{capture_efficiency:.0%}（唯一论文 / 总返回）")
        if suggested:
            lines.append(f"   建议补充检索词：{'、'.join(suggested)}")
        lines.append(f"   📋 {decision}")
        lines.append("   报告已存：" + str(report_path))
        return "\n".join(lines)

    def h_parse_paper(self, args: dict) -> str:
        """解析单篇论文。"""
        from literature_agent.parser import DocumentParser
        filepath = args["filepath"]

        parser = DocumentParser()
        doc = parser.parse(filepath)

        # Store in session state
        papers = self.survey_state.setdefault("parsed_papers", {})
        papers[filepath] = {
            "title": doc.title,
            "authors": doc.authors,
            "abstract": doc.abstract[:500],
            "materials": doc.materials_mentioned[:20],
            "properties": doc.properties_mentioned[:20],
            "methods": doc.methods_mentioned[:20],
            "sections": len(doc.sections),
            "references": len(doc.references),
            "engine": doc.parse_engine,
        }

        return (
            f"✅ Parsed: {doc.title or filepath}\n"
            f"   Authors: {', '.join(doc.authors[:5])}\n"
            f"   Abstract: {doc.abstract[:300]}...\n"
            f"   Sections: {len(doc.sections)} | References: {len(doc.references)}\n"
            f"   Materials: {', '.join(doc.materials_mentioned[:10])}\n"
            f"   Properties: {', '.join(doc.properties_mentioned[:10])}\n"
            f"   Engine: {doc.parse_engine} ({doc.parse_time_seconds}s)"
        )

    def h_extract_knowledge(self, args: dict) -> str:
        """整理论文摘要为可读文本，供 Agent 直接阅读分析。

        不做结构化 JSON 抽取——Agent 本身有足够的推理能力，
        直接从论文摘要中识别材料、性质、关系和 Gap。
        """
        import json as _json
        from pathlib import Path as _Path

        papers_json = args.get("papers_json", "{}")
        filepath = args.get("filepath", "")

        if filepath:
            fp = _Path(filepath)
            if not fp.exists():
                fp = _Path("workspace") / filepath
            if fp.exists():
                papers_json = fp.read_text(encoding="utf-8")
            else:
                return f"❌ File not found: {filepath}"

        try:
            papers = _json.loads(papers_json)
        except _json.JSONDecodeError:
            return f"❌ Invalid JSON for papers_json."

        if not papers:
            return "❌ No papers to process."

        # ── 整理为可读 Markdown 摘要 ──
        out_dir = _Path("workspace/outputs/literature_survey")
        out_dir.mkdir(parents=True, exist_ok=True)

        md_lines = [
            f"# Literature Survey — Paper Summaries",
            f"\n**Total papers:** {len(papers)}",
            f"**Generated:** {__import__('datetime').datetime.now().isoformat()}\n",
            "---\n",
        ]

        # 统计来源分布
        sources = {}
        keywords_all = set()
        for pid, text in papers.items():
            text_str = str(text)
            # 尝试提取来源信息
            if 'sciverse' in text_str.lower():
                sources['sciverse'] = sources.get('sciverse', 0) + 1
            elif 'arxiv' in text_str.lower():
                sources['arxiv'] = sources.get('arxiv', 0) + 1
            else:
                sources['unknown'] = sources.get('unknown', 0) + 1
            # 收集关键词
            for kw in ['MOF', 'CO2', 'adsorption', 'capture', 'selectivity',
                        'perovskite', 'catalysis', 'battery', 'stability',
                        'synthesis', 'ZIF', 'UiO', 'MIL', 'HKUST']:
                if kw.lower() in text_str.lower():
                    keywords_all.add(kw)

        md_lines.append(f"**Sources:** {', '.join(f'{k}({v})' for k, v in sources.items())}")
        md_lines.append(f"**Common keywords:** {', '.join(sorted(keywords_all)[:20])}")
        md_lines.append("\n---\n")

        # 逐篇列出摘要
        for i, (pid, paper_text) in enumerate(papers.items(), 1):
            text = str(paper_text)
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            title = lines[0][:150] if lines else pid
            # 尝试提取额外字段
            doi = ""
            authors = ""
            year = ""
            body_lines = []
            for line in lines[1:]:
                if line.lower().startswith("doi:") or line.lower().startswith("doi "):
                    doi = line.replace("DOI:", "").replace("doi:", "").strip()
                elif line.lower().startswith("authors:") or line.lower().startswith("author:"):
                    authors = line.replace("Authors:", "").replace("authors:", "").strip()[:200]
                elif line.lower().startswith("year:") or line.lower().startswith("year "):
                    year = line.replace("Year:", "").replace("year:", "").strip()
                else:
                    body_lines.append(line)

            md_lines.append(f"### {i}. {title}")
            if authors:
                md_lines.append(f"**Authors:** {authors}")
            if year:
                md_lines.append(f"**Year:** {year}")
            if doi:
                md_lines.append(f"**DOI:** {doi}")
            md_lines.append(f"**ID:** `{pid}`")
            # 摘要正文
            body = " ".join(body_lines)[:800]
            if body:
                md_lines.append(f"\n{body}")
            md_lines.append("")

        # 写入文件
        summary_path = out_dir / "paper_summaries.md"
        summary_path.write_text("\n".join(md_lines), encoding="utf-8")
        self.survey_state["paper_summary_path"] = str(summary_path)

        # 注意：不生成 JSON 知识图谱——知识图谱由 Agent 阅读摘要后自行撰写
        # （workspace/outputs/literature_survey/knowledge_graph.md，Markdown 格式）。
        self.survey_state["knowledge_graph_path"] = str(out_dir / "knowledge_graph.md")

        return (
            f"✅ Paper summaries organized: {len(papers)} papers\n"
            f"   Markdown: {summary_path}\n"
            f"   Sources: {sources}\n\n"
            f"📖 Next: Agent should read_file {summary_path} to analyze the literature, "
            f"then write_file 自己的知识图谱 workspace/outputs/literature_survey/knowledge_graph.md"
            f"（材料/性质/数值/关系，Markdown 格式），"
            f"then call analyze_gaps() to identify research gaps, "
            f"then generate_report() to produce the final survey."
        )

    def h_analyze_gaps(self, args: dict) -> str:
        """指示主 Agent 自己阅读论文摘要并撰写 Gap 分析报告。

        本工具不做 LLM 调用——主 Agent 持有完整上下文，
        应自行 read_file 论文摘要 + write_file 输出 gap_report.md。
        """
        from pathlib import Path as _Path
        import json as _json

        summary_path = self.survey_state.get(
            "paper_summary_path",
            "workspace/outputs/literature_survey/paper_summaries.md",
        )
        search_path = "workspace/data/literature_cache/search_results.json"

        has_summary = _Path(summary_path).exists()
        has_search = _Path(search_path).exists()

        if not has_summary and not has_search:
            return "❌ 没有论文摘要。请先执行 search_papers 然后 extract_knowledge。"

        # 统计
        paper_count = 0
        if has_summary:
            paper_count = _Path(summary_path).read_text(encoding="utf-8").count("### ")

        # Gap 报告由 Agent 自行撰写为 Markdown（gap_report.md），不再生成占位 JSON
        out_dir = _Path("workspace/outputs/literature_survey")
        out_dir.mkdir(parents=True, exist_ok=True)
        self.survey_state["gap_report_path"] = str(out_dir / "gap_report.md")

        return (
            f"📋 Gap 分析任务已就绪（{paper_count} 篇论文摘要可用）。\n\n"
            f"请主 Agent 按以下步骤自行完成：\n"
            f"1. read_file {summary_path} — 阅读全部论文摘要\n"
            f"2. 基于摘要识别：矛盾结论、缺失知识连接、未探索的材料-性质空间\n"
            f"3. write_file workspace/outputs/literature_survey/gap_report.md — 输出结构化 Gap 报告\n\n"
            f"报告格式要求：\n"
            f"  - 每个 Gap 标注类型（矛盾/缺失连接/未探索）、严重程度（高/中/低）\n"
            f"  - 附论文 ID 作为证据来源\n"
            f"  - 给出可操作的验证建议\n"
            f"  - 全部使用中文撰写\n"
        )

    def h_audit_knowledge_graph(self, args: dict) -> str:
        """审计 Agent 手写的 Markdown 知识图谱：数值冲突 / 实体重复 / 溯源缺失。"""
        from literature_agent.extractor import audit_markdown_kg
        from pathlib import Path as _Path
        import json as _json

        source_text = self._load_knowledge_source()
        if not source_text:
            return (
                "❌ 找不到知识来源（knowledge_graph.md / paper_summaries.md）。\n"
                "请先 write_file 自己的知识图谱 "
                "workspace/outputs/literature_survey/knowledge_graph.md，然后重试。"
            )

        audit = audit_markdown_kg(source_text)
        out_dir = _Path("workspace/outputs/literature_survey")
        out_dir.mkdir(parents=True, exist_ok=True)

        # JSON
        json_path = out_dir / "knowledge_graph_audit.json"
        json_path.write_text(_json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

        # Markdown
        st = audit["stats"]
        md_lines = [
            "# 知识图谱审计报告",
            "",
            f"**材料**：{st['materials']} | **性质记录**：{st['property_records']} | "
            f"**数值冲突**：{st['conflicts']} | **实体重复**：{st['duplicates']} | "
            f"**溯源缺失**：{st['no_provenance']}",
            "",
            "## 1. 数值冲突（→ 矛盾型 Research Gap 候选）",
            "",
        ]
        if audit["conflicts"]:
            for i, c in enumerate(audit["conflicts"], 1):
                md_lines.append(f"### {i}. {c['material']} / {c['property']}（{c['unit']}）")
                md_lines.append(f"- 最小值：{c['values'][0]}（来源 {c['min_paper'] or '未知'}）")
                md_lines.append(f"- 最大值：{c['values'][-1]}（来源 {c['max_paper'] or '未知'}）")
                md_lines.append("")
        else:
            md_lines.append("- 未发现显著数值冲突")
            md_lines.append("")
        md_lines += ["## 2. 实体重复", ""]
        if audit["duplicates"]:
            for d in audit["duplicates"]:
                md_lines.append(f"- {' / '.join(d['names'])} → 建议统一为一种写法")
        else:
            md_lines.append("- 未发现重复写法")
        md_lines += ["", "## 3. 溯源缺失（数值无论文 ID）", ""]
        if audit["no_provenance_records"]:
            for r in audit["no_provenance_records"][:20]:
                md_lines.append(f"- {r['material']} / {r['property']} = {r['value']} {r['unit']}")
        else:
            md_lines.append("- 全部数值均有论文 ID 支撑")
        md_lines.append("")
        md_path = out_dir / "knowledge_graph_audit.md"
        md_path.write_text("\n".join(md_lines), encoding="utf-8")

        self.survey_state["knowledge_audit"] = audit
        self.survey_state["knowledge_audit_path"] = str(md_path)

        lines = [
            "✅ 知识图谱审计完成",
            f"   材料 {st['materials']} | 性质记录 {st['property_records']} | "
            f"冲突 {st['conflicts']} | 重复 {st['duplicates']} | 溯源缺失 {st['no_provenance']}",
            f"   审计报告：{md_path}",
        ]
        if audit["conflicts"]:
            lines.append("   ⚠️ 矛盾型 Gap 候选（数值冲突）：")
            for c in audit["conflicts"][:5]:
                lines.append(
                    f"   - {c['material']} / {c['property']}: "
                    f"{c['values'][0]} vs {c['values'][-1]} {c['unit']}"
                )
        if audit["duplicates"]:
            lines.append("   🔁 重复写法：")
            for d in audit["duplicates"][:5]:
                lines.append(f"   - {' / '.join(d['names'])}")
        lines.append(
            "   下一步：read_file 审计报告 → 修正知识图谱（统一写法/补论文 ID）→ "
            "将数值冲突写入 gap_report.md 作为矛盾型 Gap"
        )
        return "\n".join(lines)

    def h_generate_report(self, args: dict) -> str:
        """指示主 Agent 自己撰写最终调研报告。

        本工具不做 LLM 调用——主 Agent 持有全部论文摘要和 Gap 分析的上下文，
        应自行 write_file 输出 survey_report.md。
        """
        from pathlib import Path as _Path
        import json as _json

        topic = args.get("topic", "Literature Survey")
        out_dir = _Path("workspace/outputs/literature_survey")
        out_dir.mkdir(parents=True, exist_ok=True)

        summary_path = self.survey_state.get("paper_summary_path",
            "workspace/outputs/literature_survey/paper_summaries.md")
        gap_path = "workspace/outputs/literature_survey/gap_report.md"

        has_summary = _Path(summary_path).exists()
        has_gap = _Path(gap_path).exists()
        paper_count = _Path(summary_path).read_text(encoding="utf-8").count("### ") if has_summary else 0

        return (
            f"📋 调研报告任务已就绪（主题：{topic}，{paper_count} 篇论文）。\n\n"
            f"请主 Agent 按以下步骤自行完成：\n"
            f"1. read_file {summary_path} — 回顾论文摘要\n"
            + (f"2. read_file {gap_path} — 回顾 Gap 分析\n" if has_gap else "") +
            f"3. write_file workspace/outputs/literature_survey/survey_report.md — 输出完整调研报告\n\n"
            f"报告结构：\n"
            f"  # 文献调研报告：{topic}\n"
            f"  ## 1. 执行摘要\n"
            f"  ## 2. 文献综述（按主题/材料/方法组织）\n"
            f"  ## 3. 关键材料与性质对比（含量化数据表格）\n"
            f"  ## 4. 研究空白与未来方向\n"
            f"  ## 5. 参考文献（含 DOI 可追溯）\n\n"
            f"要求：全部使用中文撰写，论文标题和作者名保留原文，每个结论标注来源论文 ID。"
        )


def build_tool_manager(task_type: str, bench: str, memory_dir: Path,
                       print_fn: Callable, event_bus: EventBus = None) -> Tuple[ToolManager, ToolHandlers]:
    """
    Factory: create a fully-registered ToolManager with all 9 tools.

    Returns (manager, handlers) — manager for execution, handlers for Agent to inject callbacks.
    """
    handlers = ToolHandlers(task_type=task_type, bench=bench, memory_dir=memory_dir, print_fn=print_fn)
    manager = ToolManager(event_bus=event_bus, print_fn=print_fn)

    # Register all tools
    manager.register("think", handlers.h_think)
    manager.register("list_files", handlers.h_list_files)
    manager.register("read_file", handlers.h_read_file)
    manager.register("write_file", handlers.h_write_file)
    manager.register("edit_file", handlers.h_edit_file)
    manager.register("run_shell", handlers.h_run_shell)
    manager.register("start_shell", handlers.h_start_shell)
    manager.register("check_shell", handlers.h_check_shell)
    manager.register("kill_shell", handlers.h_kill_shell)
    manager.register("stop", handlers.h_stop)
    # Literature survey tools
    manager.register("search_papers", handlers.h_search_papers)
    manager.register("assess_search_coverage", handlers.h_assess_search_coverage)
    manager.register("parse_paper", handlers.h_parse_paper)
    manager.register("get_full_text", handlers.h_get_full_text)
    manager.register("extract_knowledge", handlers.h_extract_knowledge)
    manager.register("analyze_gaps", handlers.h_analyze_gaps)
    manager.register("audit_knowledge_graph", handlers.h_audit_knowledge_graph)
    manager.register("generate_report", handlers.h_generate_report)
    # Route A: Discovery tools
    manager.register("generate_hypotheses", handlers.h_generate_hypotheses)
    manager.register("run_discovery_search", handlers.h_run_discovery_search)
    manager.register("validate_discovery", handlers.h_validate_discovery)
    manager.register("generate_discovery_report", handlers.h_generate_discovery_report)

    return manager, handlers
