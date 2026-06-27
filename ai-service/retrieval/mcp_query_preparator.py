"""McpQueryPreparator — MCP 场景查询准备器。

职责：
    1. jieba 关键词提取 — 从 Agent 构造好的精确 query 中提取实体/术语，给 BM25 稀疏检索补充信号
    2. context_hint 透传 — Agent 已有的用户背景信息不做检索词，仅注入 LLM 生成阶段
    3. focus_aspects / doc_type — 元数据过滤参数的归一化

与 Web Chat 的 ChatQueryPreparator (QueryRewriter + IntentRouter) 的区别：
    - Web Chat: LLM 消解指代 + 补全术语（语义收敛，模糊→精确）
    - MCP:     纯本地关键词提取（语义扩展，精确→丰富）
    - 服务端零 LLM 调用，信任 Agent 已构造好 query
"""

import re
from dataclasses import dataclass, field

from common import get_logger

logger = get_logger(__name__)

# 中文停用词表（精简版，覆盖企业知识库场景中无检索价值的词）
_CN_STOPWORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "什么", "怎么", "如何", "怎样", "哪个", "哪些", "为什么", "可以", "能",
    "能够", "应该", "需要", "还是", "或者", "以及", "并且", "但是", "因为",
    "所以", "如果", "虽然", "然后", "之后", "之前", "之", "的", "吗",
    "呢", "吧", "啊", "哦", "嗯", "请", "帮", "给", "把", "被", "让",
    "从", "对", "向", "与", "及", "其", "等", "或", "且", "而", "所",
    "该", "此", "将", "已", "正", "再", "又", "才", "刚", "还", "便",
    "只", "没", "更", "最", "较", "非常", "十分", "特别", "相当",
    "这个", "那个", "这里", "那里", "这样", "那样", "各种", "其他",
    "使用", "进行", "通过", "根据", "按照", "关于", "对于", "为了",
    "一个", "一些", "一下", "一点", "一种", "一部分", "一种",
}

# 纯标点正则（用于过滤无意义 token）
_PUNCT_ONLY = re.compile(
    r'^[，。！？、；：“”‘’（）【】《》\s,.!?;:()\[\]{}\#@\$\%^&*+=]+$'
)

# 有价值的关键词模式（不依赖分词）
_ENTITY_PATTERNS = [
    # 版本号: v3.0, 22.04, 1.2.3
    re.compile(r'(?:v|V)?\d+(?:\.\d+)+(?:-[a-zA-Z0-9]+)?'),
    # 错误码/编号: Error 10061, ERR-500, #12345
    re.compile(r'(?:[A-Z]{2,}[-\s]?)?\d{3,}'),
    # 文件名/命令: setup.sh, docker-compose.yaml, nginx.conf
    re.compile(r'[a-zA-Z][a-zA-Z0-9._-]*\.[a-zA-Z]{1,10}'),
    # 技术术语: 驼峰/下划线命名
    re.compile(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+'),
]


def extract_keywords(
    query: str,
    max_keywords: int = 10,
) -> list[str]:
    """从 query 中提取关键词，用于 BM25 稀疏检索。

    提取策略（无 LLM，纯本地）：
        1. 正则提取实体模式（版本号、错误码、文件名、技术术语）
        2. jieba 分词 + 停用词过滤 + 词长过滤
        3. 去重去噪，保留 top-N

    注意：context_hint 不参与关键词提取——其语义是"Agent 已知背景"，
    不是检索关键词来源，仅注入 ask_expert 的 LLM 生成阶段。

    Args:
        query: Agent 构造的搜索查询
        max_keywords: 最大关键词数

    Returns:
        去重后的关键词列表，如 ["XX系统", "3.0", "Ubuntu", "22.04", "部署"]
    """
    text = query

    keywords: list[str] = []

    # Step 1: 正则提取实体模式
    for pattern in _ENTITY_PATTERNS:
        for match in pattern.finditer(text):
            kw = match.group().strip()
            if kw and kw not in keywords:
                keywords.append(kw)

    # Step 2: jieba 分词 + 过滤
    try:
        import jieba
        words = jieba.cut(text)
        for w in words:
            w = w.strip()
            # 过滤条件
            if not w:
                continue
            if len(w) < 2 and not w.isdigit():  # 单字且非数字 → 太弱
                continue
            if w in _CN_STOPWORDS:
                continue
            if _PUNCT_ONLY.match(w):
                continue  # 纯标点
            if w not in keywords:
                keywords.append(w)
    except ImportError:
        # 降级：按空格/标点简单切分
        tokens = re.split(r'[\s,，。！？、；：""''（）【】《》]+', text)
        for t in tokens:
            t = t.strip()
            if t and len(t) >= 2 and t not in _CN_STOPWORDS:
                if t not in keywords:
                    keywords.append(t)

    # Step 3: 截断
    if len(keywords) > max_keywords:
        keywords = keywords[:max_keywords]

    logger.debug(f"关键词提取: query='{query[:60]}' → keywords={keywords}")
    return keywords


@dataclass
class McpPreparedQuery:
    """MCP 查询准备结果。"""
    query: str                           # 原始 query（不受影响）
    keywords: list[str] = field(default_factory=list)
    top_k: int = 10                      # MCP 场景默认 10
    context_hint: str | None = None      # 透传给 LLM 生成阶段
    focus_aspects: list[str] | None = None
    doc_type: str | None = None


_ASPECT_MAP: dict[str, list[str]] = {
    "installation":   ["安装", "部署", "配置环境"],
    "configuration":  ["配置", "设置", "参数"],
    "troubleshooting": ["故障", "报错", "错误", "排查", "解决"],
    "api_reference":   ["API", "接口", "参数说明", "返回值"],
    "best_practices":  ["最佳实践", "推荐", "建议方案"],
    "security":        ["安全", "权限", "认证", "加密"],
    "version_history": ["版本", "更新日志", "changelog", "变更"],
}


def _resolve_focus_keywords(focus_aspects: list[str] | None) -> list[str]:
    """将 focus_aspects 映射为中文关键词补充。"""
    if not focus_aspects:
        return []
    extra = []
    for aspect in focus_aspects:
        if aspect in _ASPECT_MAP:
            extra.extend(_ASPECT_MAP[aspect])
    return extra


class McpQueryPreparator:
    """MCP 查询准备器 — 纯本地处理，零 LLM 调用。"""

    def prepare(
        self,
        query: str,
        top_k: int = 10,
        context_hint: str | None = None,
        focus_aspects: list[str] | None = None,
        doc_type: str | None = None,
    ) -> McpPreparedQuery:
        """准备查询。

        Args:
            query: Agent 构造的搜索查询（已经过协议约束，假设质量较高）
            top_k: 期望返回结果数
            context_hint: Agent 已知的用户背景，不作为检索词
            focus_aspects: 限定关注的方面
            doc_type: 限定文档类型

        Returns:
            McpPreparedQuery
        """
        # 关键词提取：query + focus_aspects 翻译词
        extra_kw = _resolve_focus_keywords(focus_aspects)
        combined_query = query
        if extra_kw:
            combined_query = f"{query} {' '.join(extra_kw)}"

        keywords = extract_keywords(combined_query)

        logger.info(
            f"MCP 查询准备: query='{query[:60]}', keywords={keywords}, "
            f"aspects={focus_aspects}, doc_type={doc_type}"
        )

        return McpPreparedQuery(
            query=query,
            keywords=keywords,
            top_k=top_k,
            context_hint=context_hint,
            focus_aspects=focus_aspects,
            doc_type=doc_type,
        )
