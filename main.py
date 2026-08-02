"""
GOAI 材料科学文献调研 Agent — 主入口
=====================================
接收命令行参数，启动 Prospector 系统，在预算内自主完成文献调研。
四阶段流程：检索 → 知识抽取 → Gap 分析 → 报告生成

用法示例:
    python main.py --topic "MOF materials for CO2 capture"
    python main.py --topic "perovskite solar cell stability" --budget 3600 --fresh
"""
import argparse
import os
import sys


def run_survey(output_dir: str, budget: int = None,
               fresh_start: bool = False, research_topic: str = ""):
    """启动文献调研 Agent。

    Agent 在预算内完成：文献检索、知识抽取、Gap分析、报告生成，
    最终输出结构化调研报告（Markdown + JSON）和过程日志。

    参数:
        output_dir: 输出根目录
        budget: 时间预算（秒），默认从配置读取 7200
        fresh_start: 是否强制忽略已有 checkpoint
        research_topic: 文献调研主题
    """
    from prospector.agent import Prospector

    print(f"\n{'='*60}")
    print(f"  📚 Literature Survey Agent")
    print(f"  Topic: {research_topic}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}")

    brain = Prospector(
        output_dir=output_dir,
        budget=budget,
        fresh_start=fresh_start,
        research_topic=research_topic,
    )

    crashed = False
    try:
        brain.run()
        print(f"\n[OK] Survey completed successfully.")
    except KeyboardInterrupt:
        print(f"\n[ABORT] User interrupted", file=sys.stderr)
        crashed = True
    except Exception as e:
        print(f"\n[FAIL] Survey crashed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        crashed = True

    if crashed:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="GOAI Literature Survey Agent — 材料科学文献调研智能体"
    )
    parser.add_argument("--topic", default="",
                       help="文献调研主题，如 'MOF materials for CO2 capture'")
    parser.add_argument("--output", default="workspace/outputs/",
                       help="输出根目录")
    parser.add_argument("--fresh", action="store_true",
                       help="强制从头开始，忽略已有 checkpoint")
    parser.add_argument("--budget", type=int, default=None,
                       help="时间预算（秒），默认 7200（2小时）")

    args = parser.parse_args()

    if not args.topic:
        print("Error: --topic is required. Example: --topic 'perovskite solar cells'",
              file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)
    run_survey(args.output, args.budget, args.fresh, args.topic)
    print("\n=== Survey completed ===")


if __name__ == "__main__":
    main()
