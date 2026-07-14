package com.kes.auth.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * 检索质量反馈服务（精简版 — 仪表盘已迁移到 Langfuse）。
 * 仅保留用户反馈提交，查询功能由 Langfuse 替代。
 */
@Service
public class FeedbackService {

    private static final Logger log = LoggerFactory.getLogger(FeedbackService.class);

    private final JdbcTemplate jdbc;

    public FeedbackService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * 提交用户反馈 — UPDATE 已有 trace 的 rating 和 reason。
     */
    public void submitFeedback(String traceId, String rating, String reason) {
        String sql = """
                UPDATE retrieval_feedback
                SET rating = ?,
                    feedback_reason = ?,
                    feedback_at = NOW()
                WHERE id = ?::uuid
                """;
        try {
            int updated = jdbc.update(sql, rating, reason, traceId);
            if (updated > 0) {
                log.info("反馈已提交: trace_id={}, rating={}", traceId, rating);
            } else {
                log.warn("反馈提交失败，trace 不存在: {}", traceId);
            }
        } catch (Exception e) {
            log.warn("提交反馈失败（表可能尚未创建）: {}", e.getMessage());
        }
    }
}
