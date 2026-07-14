"""JudgeEvaluator — LLM-as-a-Judge 自动评估（v1）。

评估三个维度:
  - faithfulness: 忠实度 — 答案是否仅基于检索结果，有无幻觉
  - answer_relevance: 答案相关性 — 是否回答了用户问题
  - context_relevance: 上下文相关性 — 检索到的 chunks 是否与问题相关

使用 SLM 做评估（成本低于主 LLM），结构化 JSON 输出。
异步执行，不阻塞用户响应。

用法:
    judge = JudgeEvaluator(slm)
    scores = await judge.evaluate(
        query="如何配置...",
        answer="根据文档...",
        chunks=[...],
    )
    # → {"faithfulness": 0.9, "answer_relevance": 0.85, "context_relevance": 0.8}
"""

import json
import re
import time

from common import get_logger

logger = get_logger(__name__)

# 评估 prompt — v2: 5档 rubric + few-shot + 先推理后打分
_JUDGE_PROMPT = """你是 RAG 系统质量评估专家。根据用户问题、检索到的文档、生成的答案，对答案质量进行三维评分。

## 用户问题
{query}

## 检索到的文档片段（共 {chunk_count} 条）
{chunks_text}

## 生成的答案
{answer}{ground_truth}

## 评分维度与 Rubric

### 1. faithfulness（忠实度）— 答案是否严格基于检索结果？
检查答案中每个关键陈述能否在「检索到的文档片段」中找到原文支撑。

| 分数 | 标准 |
|------|------|
| 1.0 | 所有关键陈述都能在文档中找到原文支撑，无任何编造 |
| 0.75 | 主要结论有支撑，但有一处次要细节文档未提及 |
| 0.5 | 核心结论有支撑，但混入了1-2处文档中没有的信息 |
| 0.25 | 只有少部分内容有支撑，大量信息超出文档范围 |
| 0.0 | 答案完全编造，或与文档内容矛盾 |

### 2. answer_relevance（答案相关性）— 答案是否直接回答了用户问题？
检查答案是否完整覆盖了用户问题的所有方面。

| 分数 | 标准 |
|------|------|
| 1.0 | 完整、直接回答了问题的所有要点 |
| 0.75 | 回答了主要问题，但遗漏了一个次要方面 |
| 0.5 | 部分回答了问题，遗漏了至少一半要点 |
| 0.25 | 只轻微触及问题，基本没有有效回答 |
| 0.0 | 答非所问，或拒绝回答 |

### 3. context_relevance（上下文相关性）— 检索到的文档与问题的匹配度？
判断检索结果是否与用户问题相关，是否有大量噪声。

| 分数 | 标准 |
|------|------|
| 1.0 | 所有文档片段都与问题高度相关 |
| 0.75 | 大部分相关，少量片段关联度低 |
| 0.5 | 约一半相关，一半属于噪声 |
| 0.25 | 只有少量片段相关，多数不相关 |
| 0.0 | 所有片段都与问题无关 |

## Few-Shot 示例

### 示例 1 — 高质量答案
用户问题：阿里巴巴的合规负责人指什么？
检索文档：[1] "合规负责人"指阿里巴巴集团内审合规部和法务部的部门负责人。
生成答案：合规负责人是指阿里巴巴集团内审合规部和法务部的部门负责人。

评分过程：
- faithfulness: 答案的两个要点（"内审合规部"+"法务部的部门负责人"）在文档[1]中均有原文。→ 1.0
- answer_relevance: 直接回答了"合规负责人指什么"。→ 1.0
- context_relevance: 文档[1]直接定义了"合规负责人"，高度相关。→ 1.0

### 示例 2 — 部分幻觉
用户问题：拥抱变化包含哪几个层次？
检索文档：[1] 拥抱变化——迎接变化，勇于创新。适应公司的日常变化，不抱怨。面对变化，理性对待，充分沟通。
生成答案：拥抱变化包含5个层次：1.适应日常变化 2.理性对待变化 3.自我调整带动同事 4.建立新方法 5.创造变化突破绩效。此外还包括"主动学习新技术"。

评分过程：
- faithfulness: "适应日常变化""理性对待变化"有文档[1]支撑。"自我调整""建立新方法""创造变化"等虽然文档[1]提到了但表述不同，可以考虑是否有隐含支撑。但"主动学习新技术"在文档中完全没有 → 0.75
- answer_relevance: 直接回答了"哪几个层次"，列举了5点且额外加了信息 → 0.75
- context_relevance: 文档[1]直接讨论拥抱变化，高度相关 → 1.0

### 示例 3 — 答案与参考答案对比
用户问题：合规负责人是指谁？
参考答案：合规负责人是指阿里巴巴集团内审合规部和法务部的部门负责人。
检索文档：[1] "合规负责人"指内审合规部和法务部的部门负责人。
系统回答：合规负责人是法务部的部门负责人。

评分过程：
- faithfulness: "法务部的部门负责人"在文档[1]中有支撑 → 1.0
- answer_relevance: 直接回答了问题 → 1.0
- context_relevance: 文档[1]直接相关 → 1.0
- answer_correctness: 回答只提了"法务部"，遗漏了"内审合规部"，属于关键事实遗漏 → 0.5

## 输出格式

先逐维度写出推理过程，最后输出 JSON：

**faithfulness 推理**：（逐条检查答案陈述 vs 文档原文）
**answer_relevance 推理**：（检查是否覆盖了问题的所有要点）
**context_relevance 推理**：（检查文档片段与问题的匹配度）
**answer_correctness 推理**：（对比参考答案 vs 系统回答，检查关键事实覆盖度和准确性）

```json
{{
  "faithfulness": 0.XX,
  "answer_relevance": 0.XX,
  "context_relevance": 0.XX,
  "answer_correctness": 0.XX
}}
```

只输出推理和 JSON，不要额外评论。"""


# 截断参数
_MAX_CHUNKS_FOR_JUDGE = 5
_MAX_CHUNK_CHARS = 300
_MAX_ANSWER_CHARS = 800


class JudgeEvaluator:
    """LLM-as-a-Judge 评估器。

    用 SLM 对 RAG 输出做三维自动评分。
    """

    def __init__(self, slm):
        """初始化。

        Args:
            slm: 小模型实例（BaseLLM），用于降本评估
        """
        self._slm = slm

    async def evaluate(
        self,
        query: str,
        answer: str,
        chunks: list | None = None,
        ground_truth: str | None = None,
    ) -> dict:
        """执行四维评估。

        Args:
            query: 用户原始问题
            answer: LLM 生成的答案
            chunks: 检索到的 ScoredChunk 列表（或含 content 的 dict）
            ground_truth: 参考答案（可选，用于 answer_correctness 评分）

        Returns:
            {
                "faithfulness": float,
                "answer_relevance": float,
                "context_relevance": float,
                "answer_correctness": float | None,
                "model": str,
                "latency_ms": int,
            }
        """
        if self._slm is None:
            logger.warning("SLM 未初始化，跳过 Judge 评估")
            return self._empty_result()

        chunks = chunks or []
        start = time.monotonic()

        try:
            # 构建 chunks 文本（截断）
            chunk_texts = []
            for i, c in enumerate(chunks[: _MAX_CHUNKS_FOR_JUDGE]):
                content = c.content if hasattr(c, "content") else c.get("content", "")
                source = c.source_file if hasattr(c, "source_file") else c.get("source_file", "")
                chunk_texts.append(
                    f"[{i + 1}] 来源: {source}\n{content[:_MAX_CHUNK_CHARS]}"
                )

            chunks_text = "\n\n".join(chunk_texts) if chunk_texts else "（无检索结果）"

            has_gt = ground_truth and ground_truth.strip()
            prompt = _JUDGE_PROMPT.format(
                query=query,
                chunk_count=len(chunk_texts),
                chunks_text=chunks_text,
                answer=answer[:_MAX_ANSWER_CHARS],
                ground_truth=f"\n## 参考答案\n{ground_truth.strip()}" if has_gt else "",
            )

            response_wrapper = await self._slm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )

            scores = self._parse_response(response)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            logger.info(
                f"Judge 评估完成: faithfulness={scores['faithfulness']:.2f}, "
                f"answer_relevance={scores['answer_relevance']:.2f}, "
                f"context_relevance={scores['context_relevance']:.2f}, "
                f"answer_correctness={scores.get('answer_correctness', 'N/A')}, "
                f"latency={elapsed_ms}ms"
            )

            return {
                "faithfulness": scores["faithfulness"],
                "answer_relevance": scores["answer_relevance"],
                "context_relevance": scores["context_relevance"],
                "answer_correctness": scores.get("answer_correctness"),
                "model": self._slm.get_model_name() if hasattr(self._slm, "get_model_name") else "slm",
                "latency_ms": elapsed_ms,
            }

        except Exception as e:
            logger.warning(f"Judge 评估失败: {e}")
            return self._empty_result()

    @staticmethod
    def _parse_response(response: str) -> dict:
        """解析 SLM 响应的 JSON。"""
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"^```(?:json)?\s*", "", response)
            response = re.sub(r"\s*```$", "", response)

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return {"faithfulness": 0.0, "answer_relevance": 0.0, "context_relevance": 0.0}
            else:
                return {"faithfulness": 0.0, "answer_relevance": 0.0, "context_relevance": 0.0}

        return {
            "faithfulness": max(0.0, min(1.0, float(data.get("faithfulness", 0.0)))),
            "answer_relevance": max(0.0, min(1.0, float(data.get("answer_relevance", 0.0)))),
            "context_relevance": max(0.0, min(1.0, float(data.get("context_relevance", 0.0)))),
            "answer_correctness": max(0.0, min(1.0, float(data.get("answer_correctness", 0.0)))) if "answer_correctness" in data else None,
        }

    @staticmethod
    def _empty_result() -> dict:
        return {
            "faithfulness": 0.0,
            "answer_relevance": 0.0,
            "context_relevance": 0.0,
            "answer_correctness": None,
            "model": "",
            "latency_ms": 0,
        }
