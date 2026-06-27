package com.kes.document.service;

import com.kes.AbstractIntegrationTest;
import com.kes.auth.model.KnowledgeBase;
import com.kes.auth.repository.KnowledgeBaseRepository;
import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentMetaRepository;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

/**
 * DocumentService 集成测试 — 文档生命周期状态机。
 * 使用真实数据库验证软删除/恢复/永久删除流程。
 */
class DocumentServiceIT extends AbstractIntegrationTest {

    @Autowired private DocumentMetaRepository docRepo;
    @Autowired private DocumentTrashService trashService;
    @Autowired private DocumentQueryService queryService;
    @Autowired private KnowledgeBaseRepository kbRepo;

    private String kbId;
    private String docId;

    @BeforeEach
    @Transactional
    void setUpData() {
        kbId = UUID.randomUUID().toString();
        kbRepo.save(new KnowledgeBase(kbId, "space-x", "测试KB", "", "space_wide", "admin"));

        docId = UUID.randomUUID().toString();
        DocumentMeta doc = new DocumentMeta();
        doc.setId(docId);
        doc.setKbId(kbId);
        doc.setFilename("test-doc.pdf");
        doc.setFileType("pdf");
        doc.setFilePath("test/test-doc.pdf");
        doc.setStatus("active");
        doc.setApprovalStatus("approved");
        doc.setUploadedBy("admin");
        docRepo.save(doc);
    }

    @Test
    @Transactional
    void softDelete_thenRestore() {
        trashService.softDelete(docId);
        DocumentMeta deleted = queryService.getById(docId);
        assertEquals("soft_deleted", deleted.getStatus());
        assertNotNull(deleted.getDeletedAt(), "删除时间应已设置");
        assertNotNull(deleted.getExpiresAt(), "30天后过期时间应已设置");

        trashService.restore(docId);
        DocumentMeta restored = queryService.getById(docId);
        assertEquals("active", restored.getStatus());
        assertNull(restored.getDeletedAt());
        assertNull(restored.getExpiresAt());
    }

    @Test
    @Transactional
    void permanentDelete_removesRecord() {
        trashService.softDelete(docId);
        trashService.permanentDelete(docId);

        assertThrows(Exception.class, () -> queryService.getById(docId),
            "永久删除后查询应抛出异常");
    }

    @Test
    @Transactional
    void getById_notFound_throwsException() {
        assertThrows(Exception.class, () -> queryService.getById("non-existent-id"));
    }

    @Test
    @Transactional
    void list_returnsDocumentsByKbId() {
        Page<DocumentMeta> results = queryService.list(kbId, "admin", null, 1, 20);
        assertFalse(results.isEmpty(), "应返回至少一个文档");
        assertTrue(results.getContent().stream().allMatch(d ->
            kbId.equals(d.getKbId())), "所有结果应属于指定的 KB");
    }
}
