package com.kes.document.repository;

import com.kes.document.model.DocumentApproval;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface DocumentApprovalRepository extends JpaRepository<DocumentApproval, String> {

    /** 按 KB 查询审批记录（含 action_type） */
    @Query(value = """
        SELECT da.id\\:\\:text, da.document_id\\:\\:text, dm.filename, dm.file_type,
               COALESCE(u.display_name, da.submitted_by\\:\\:text) AS submitted_by,
               da.submitted_at, da.status, da.action_type
        FROM document_approvals da
        JOIN document_meta dm ON da.document_id = dm.id
        LEFT JOIN users u ON da.submitted_by = u.id
        WHERE dm.kb_id = CAST(:kbId AS uuid)
        ORDER BY da.submitted_at DESC
        """, nativeQuery = true)
    List<Object[]> findByKbId(@Param("kbId") String kbId);
}
