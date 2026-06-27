package com.kes.auth.repository;

import com.kes.auth.model.AdminActionLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AdminActionLogRepository extends JpaRepository<AdminActionLog, Long> {

    /** 按 Space 分页查询操作日志（按时间倒序） */
    Page<AdminActionLog> findBySpaceIdOrderByCreatedAtDesc(String spaceId, Pageable pageable);
}
