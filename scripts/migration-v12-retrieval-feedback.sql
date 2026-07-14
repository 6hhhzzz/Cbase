-- ============================================================
-- v12: 检索质量反馈表
-- 执行方式: psql -U kes -d kes -f migration-v12-retrieval-feedback.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS retrieval_feedback (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- 来源标识
    source          VARCHAR(20)  NOT NULL,   -- 'web_chat' | 'mcp'
    user_id         VARCHAR(50),
    space_id        VARCHAR(50),
    session_id      VARCHAR(50),

    -- 查询信息 (模块 1~2)
    original_query  TEXT         NOT NULL,
    rewritten_query TEXT,
    kb_ids          JSONB,
    keywords        JSONB,
    resolved_filters JSONB,

    -- 检索指标 (模块 3)
    retrieval_path  VARCHAR(50),            -- 'simple' | 'dag'
    top_k           INT,
    min_score       REAL,
    latency_breakdown JSONB,
    recall_stats    JSONB,
    reranked_count  INT,
    filtered_count  INT,
    llm_tokens      JSONB,

    -- 结果快照 (模块 4)
    chunks          JSONB,

    -- 生成内容 (模块 5)
    generated_response TEXT,

    -- LLM-as-a-Judge (模块 6)
    faithfulness_score   REAL,
    answer_relevance     REAL,
    context_relevance    REAL,
    judge_model          VARCHAR(50),
    judge_latency_ms     INT,

    -- 反馈结果 (模块 7)
    rating          VARCHAR(10),            -- 'like' | 'dislike'
    feedback_reason VARCHAR(100),
    feedback_at     TIMESTAMPTZ,

    -- 扩展
    extra           JSONB
);

CREATE INDEX IF NOT EXISTS idx_rf_created ON retrieval_feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_source ON retrieval_feedback(source);
CREATE INDEX IF NOT EXISTS idx_rf_rating ON retrieval_feedback(rating);
CREATE INDEX IF NOT EXISTS idx_rf_user ON retrieval_feedback(user_id);
