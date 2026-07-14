package com.kes.document.repository;

import com.kes.document.model.DocumentMeta;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface DocumentMetaRepository extends JpaRepository<DocumentMeta, String> {

    /** v3.1: 按 KB 查询所有文档（不分页，级联/永久删除用） */
    List<DocumentMeta> findAllByKbId(String kbId);

    /** v3: 按 KB + 审批状态查询 */
    Page<DocumentMeta> findByKbIdAndApprovalStatus(String kbId, String status, Pageable pageable);

    /** v3.1: 按 KB + 文档状态查询 */
    Page<DocumentMeta> findByKbIdAndStatus(String kbId, String status, Pageable pageable);

    /** v3.1: 按 KB + 文档状态查询（非分页，级联操作用） */
    List<DocumentMeta> findByKbIdAndStatus(String kbId, String status);

    /** v3.1: 按一批 KB + 文档状态查询（回收站用） */
    List<DocumentMeta> findByKbIdInAndStatus(List<String> kbIds, String status);

    /** v4: 获取一批 KB 中 inherit_permissions = false 的文档 */
    @Query("SELECT d FROM DocumentMeta d WHERE d.kbId IN :kbIds AND d.status = 'active' AND d.inheritPermissions = false")
    List<DocumentMeta> findCustomPermissionDocs(@Param("kbIds") List<String> kbIds);

    /** v4: 按 Space + 状态查询所有文档 */
    Page<DocumentMeta> findBySpaceIdAndStatus(String spaceId, String status, Pageable pageable);
}
