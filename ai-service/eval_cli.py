#!/usr/bin/env python3
"""RAGAS 评估 CLI — 离线批量评估 RAG 流水线。

用法:
    # 从最近 trace 评估
    uv run eval_cli.py --from-traces --limit 50

    # 合成评估数据集
    uv run eval_cli.py --synthetic --kb-id xxx --count 30

    # 完整评估（trace + 合成）
    uv run eval_cli.py --full --limit 50 --output my_report

    # 打印单个评估（调试用）
    uv run eval_cli.py --single --query "测试问题" --answer "测试答案"

环境要求:
    - REDIS__HOST / PGVECTOR__HOST 等环境变量（首次运行需要冷启动模型池）
    - DASHSCOPE_API_KEY（LLM 调用需要）
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# 确保当前目录在 Python path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import get_logger

logger = get_logger(__name__)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAGAS 评估 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--from-traces", action="store_true",
                        help="从 retrieval_feedback 表的已有 trace 评估")
    parser.add_argument("--synthetic", action="store_true",
                        help="从知识库文档合成评估数据集")
    parser.add_argument("--full", action="store_true",
                        help="完整评估（trace + 合成）")
    parser.add_argument("--single", action="store_true",
                        help="单次评估（调试用）")
    parser.add_argument("--limit", type=int, default=50,
                        help="最多评估 N 条 trace（默认 50）")
    parser.add_argument("--count", type=int, default=30,
                        help="合成问答对数量（默认 30）")
    parser.add_argument("--kb-id", type=str, default=None,
                        help="指定知识库 ID（合成数据或过滤 trace）")
    parser.add_argument("--output", type=str, default=None,
                        help="报告输出名称前缀（默认时间戳）")
    parser.add_argument("--query", type=str, default="",
                        help="单次评估的查询文本")
    parser.add_argument("--answer", type=str, default="",
                        help="单次评估的答案文本")
    parser.add_argument("--contexts", type=str, default="",
                        help="单次评估的上下文（逗号分隔）")
    args = parser.parse_args()

    # ── 初始化项目基础设施 ──
    llm, embedding = await _init_models()
    if llm is None:
        logger.error("无法初始化 LLM，退出")
        return 1

    from evaluation.dataset_builder import EvalDatasetBuilder
    from evaluation.ragas_runner import RagasRunner
    from evaluation.report import ReportGenerator

    runner = RagasRunner(llm=llm, embedding=embedding)
    builder = EvalDatasetBuilder()
    reporter = ReportGenerator()

    if args.single:
        return await _cmd_single(args, runner)

    if args.from_traces or args.full:
        return await _cmd_from_traces(args, runner, builder, reporter)

    if args.synthetic:
        return await _cmd_synthetic(args, runner, builder, reporter)

    # 默认：打印帮助
    parser.print_help()
    return 0


# ── 子命令 ──────────────────────────────────────────────────

async def _cmd_single(args, runner: "RagasRunner") -> int:
    """单次评估。"""
    query = args.query or input("查询: ")
    answer = args.answer or input("答案: ")
    contexts_raw = args.contexts or input("上下文（逗号分隔）: ")
    contexts = [c.strip() for c in contexts_raw.split(",") if c.strip()]

    scores = await runner.evaluate_single(
        user_input=query,
        response=answer,
        retrieved_contexts=contexts or None,
    )
    print("\n评估结果:")
    for metric, score in scores.items():
        status = "✅" if (score or 0) >= 0.8 else "⚠️" if (score or 0) >= 0.6 else "❌"
        print(f"  {status} {metric}: {score}")
    return 0


async def _cmd_from_traces(
    args, runner: "RagasRunner", builder: "EvalDatasetBuilder", reporter: "ReportGenerator"
) -> int:
    """从 trace 评估。"""
    rows = await _fetch_traces(args.limit, args.kb_id)
    if not rows:
        logger.error("没有找到 trace 记录")
        return 1

    samples = builder.from_feedback_traces(rows)
    if not samples:
        logger.error("无法从 trace 构建评估样本")
        return 1

    logger.info(f"开始评估 {len(samples)} 条样本...")
    start = time.monotonic()
    result = await runner.run_batch(samples)
    elapsed = time.monotonic() - start

    _print_result(result, elapsed)

    # 生成报告
    judge_scores = _extract_judge_scores(rows)
    json_path, md_path = reporter.generate(
        result,
        judge_comparison=judge_scores,
        output_name=args.output,
    )
    print(f"\n报告已生成: {json_path}\n          {md_path}")

    # 可选：写回数据库
    await _save_ragas_scores(rows, result.scores)
    return 0


async def _cmd_synthetic(
    args, runner: "RagasRunner", builder: "EvalDatasetBuilder", reporter: "ReportGenerator"
) -> int:
    """合成数据评估。"""
    from evaluation.synthetic_gen import SyntheticDatasetGenerator

    gen = SyntheticDatasetGenerator(
        llm=runner._llm,
        embedding=runner._embedding,
    )

    kb_id = args.kb_id
    if not kb_id:
        logger.error("合成数据需要指定 --kb-id")
        return 1

    pairs = await gen.generate(kb_id=kb_id, count=args.count)
    if not pairs:
        logger.error("合成数据生成失败")
        return 1

    samples = builder.from_synthetic_pairs(pairs)
    result = await runner.run_batch(samples)

    _print_result(result, 0)

    json_path, md_path = reporter.generate(
        result,
        output_name=args.output or f"synthetic_{kb_id[:8]}",
    )
    print(f"\n报告已生成: {json_path}\n          {md_path}")
    return 0


# ── 辅助函数 ────────────────────────────────────────────────

async def _init_models():
    """初始化 LLM 和 Embedding。"""
    try:
        from llm.model_pool import ModelPool
        pool = ModelPool()
        slm = pool.get_slm()
        embedding = pool.get_embedding()
        logger.info(f"模型池初始化成功: SLM={slm.model_name if slm else 'N/A'}")
        return slm, embedding
    except Exception as e:
        logger.warning(f"模型池初始化失败: {e}，尝试简单初始化")
        try:
            from llm.openai_compatible import OpenAICompatibleLLM
            from core.config.settings import settings

            api_key = os.getenv("DASHSCOPE_API_KEY", "")
            base_url = settings.llm.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            llm = OpenAICompatibleLLM(
                model="qwen-plus",
                api_key=api_key,
                base_url=base_url,
            )
            logger.info("使用降级 LLM 初始化")
            return llm, None
        except Exception as e2:
            logger.error(f"完全无法初始化 LLM: {e2}")
            return None, None


async def _fetch_traces(limit: int, kb_id: str | None = None) -> list[dict]:
    """从 retrieval_feedback 表获取 trace 记录。"""
    try:
        import asyncpg

        dsn = os.getenv(
            "PGVECTOR__DSN",
            f"postgresql://{os.getenv('PGVECTOR__USER', 'kes')}:"
            f"{os.getenv('PGVECTOR__PASSWORD', 'kes')}@"
            f"{os.getenv('PGVECTOR__HOST', 'localhost')}:"
            f"{os.getenv('PGVECTOR__PORT', '5432')}/"
            f"{os.getenv('PGVECTOR__DB', 'kes')}",
        )

        conn = await asyncpg.connect(dsn)
        try:
            if kb_id:
                rows = await conn.fetch(
                    """SELECT * FROM retrieval_feedback
                       WHERE kb_ids @> $1::jsonb
                       ORDER BY created_at DESC LIMIT $2""",
                    f'["{kb_id}"]', limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM retrieval_feedback ORDER BY created_at DESC LIMIT $1",
                    limit,
                )
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"读取 retrieval_feedback 失败: {e}")
        return []


def _extract_judge_scores(rows: list[dict]) -> dict[str, float]:
    """从 trace 行提取 Judge 评估分数（用于对比）。"""
    scores = {"faithfulness": [], "answer_relevance": [], "context_relevance": []}
    for row in rows:
        for key in scores:
            val = row.get(key)
            if val is not None and isinstance(val, (int, float)):
                scores[key].append(val)

    return {
        k: round(sum(v) / len(v), 4) if v else 0.0
        for k, v in scores.items()
    }


async def _save_ragas_scores(rows: list[dict], ragas_scores: dict):
    """将 RAGAS 分数写回 retrieval_feedback 表。"""
    try:
        import asyncpg

        dsn = os.getenv(
            "PGVECTOR__DSN",
            f"postgresql://{os.getenv('PGVECTOR__USER', 'kes')}:"
            f"{os.getenv('PGVECTOR__PASSWORD', 'kes')}@"
            f"{os.getenv('PGVECTOR__HOST', 'localhost')}:"
            f"{os.getenv('PGVECTOR__PORT', '5432')}/"
            f"{os.getenv('PGVECTOR__DB', 'kes')}",
        )

        import json

        conn = await asyncpg.connect(dsn)
        try:
            score_json = json.dumps(ragas_scores, ensure_ascii=False)
            for row in rows[:1]:  # 暂时只更新第一条（批量评估的结果）
                trace_id = row.get("id")
                if trace_id:
                    await conn.execute(
                        "UPDATE retrieval_feedback SET ragas_scores = $1::jsonb WHERE id = $2",
                        score_json, trace_id,
                    )
            logger.info(f"RAGAS 分数已保存到第一条 trace")
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"保存 RAGAS 分数失败（表可能缺少 ragas_scores 列）: {e}")


def _print_result(result, elapsed_s: float):
    """打印评估结果摘要。"""
    print("\n" + "=" * 50)
    print("RAGAS 评估结果")
    print("=" * 50)
    print(f"样本数: {result.sample_count}")
    if elapsed_s > 0:
        print(f"耗时: {elapsed_s:.1f}s")

    for metric, score in result.scores.items():
        if score is not None:
            status = "✅" if score >= 0.8 else "⚠️" if score >= 0.6 else "❌"
            print(f"  {status} {metric}: {score:.4f}")
        else:
            print(f"  - {metric}: N/A")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
