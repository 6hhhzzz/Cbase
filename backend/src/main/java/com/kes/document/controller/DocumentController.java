package com.kes.document.controller;

import com.kes.common.annotation.RequireSpaceAdmin;
import com.kes.auth.service.PermissionService;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.model.ApiResponse;
import com.kes.common.util.JwtUtil;
import com.kes.document.model.ApprovalItem;
import com.kes.document.model.DocumentMeta;
import com.kes.document.service.DocumentApprovalService;
import com.kes.document.service.DocumentMetadataService;
import com.kes.document.service.DocumentQueryService;
import com.kes.document.service.DocumentService;
import com.kes.document.service.DocumentTrashService;
import com.kes.document.service.MinioStorageService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.io.InputStreamResource;
import org.springframework.data.domain.Page;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 文档管理控制器 — v3 Space/KB RBAC。
 */
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService documentService;
    private final DocumentQueryService documentQueryService;
    private final DocumentApprovalService documentApprovalService;
    private final DocumentTrashService documentTrashService;
    private final DocumentMetadataService documentMetadataService;
    private final JwtUtil jwtUtil;
    private final MinioStorageService minioStorageService;
    private final PermissionService permissionService;

    private static final Set<String> INLINE_TYPES = Set.of("pdf");
    private static final Map<String, String> MIME_MAP = Map.of(
        "pdf",  "application/pdf",
        "txt",  "text/plain; charset=utf-8",
        "md",   "text/markdown; charset=utf-8",
        "html", "text/html; charset=utf-8",
        "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    );

    public DocumentController(DocumentService documentService,
                               DocumentQueryService documentQueryService,
                               DocumentApprovalService documentApprovalService,
                               DocumentTrashService documentTrashService,
                               DocumentMetadataService documentMetadataService,
                               JwtUtil jwtUtil,
                               MinioStorageService minioStorageService,
                               PermissionService permissionService) {
        this.documentService = documentService;
        this.documentQueryService = documentQueryService;
        this.documentApprovalService = documentApprovalService;
        this.documentTrashService = documentTrashService;
        this.documentMetadataService = documentMetadataService;
        this.jwtUtil = jwtUtil;
        this.minioStorageService = minioStorageService;
        this.permissionService = permissionService;
    }

    /** 上传文档到指定 KB */
    @PostMapping
    public ApiResponse<DocumentMeta> upload(
        @RequestParam("file") MultipartFile file,
        @RequestParam("kb_id") String kbId,
        @RequestParam(value = "effective_date", required = false) String effectiveDate,
        @RequestParam(value = "expiry_date", required = false) String expiryDate,
        @RequestParam(value = "version", required = false) String version,
        Authentication auth
    ) {
        String token = (String) auth.getCredentials();
        String userId = auth.getName();
        String spaceId = jwtUtil.extractSpaceId(token);
        if (!permissionService.hasPermission(userId, spaceId, kbId, "kb.write")) {
            throw new BusinessException(ErrorCode.KB_ACCESS_DENIED, "你无权向此知识库上传文档");
        }

        LocalDate effDate = (effectiveDate != null && !effectiveDate.isBlank())
            ? LocalDate.parse(effectiveDate) : LocalDate.now();
        LocalDate expDate = (expiryDate != null && !expiryDate.isBlank())
            ? LocalDate.parse(expiryDate) : null;

        DocumentMeta meta = documentService.upload(file, kbId, userId, jwtUtil.extractContextRole(token), effDate, expDate, version, spaceId);
        return ApiResponse.success(meta);
    }

    /** 管理员编辑文档的业务时效元数据 */
    @PutMapping("/{docId}/metadata")
    @RequireSpaceAdmin
    public ApiResponse<DocumentMeta> updateMetadata(
        @PathVariable String docId,
        @RequestBody Map<String, Object> body
    ) {
        DocumentMeta meta = documentMetadataService.updateMetadata(
            docId,
            (String) body.get("effective_date"),
            (String) body.get("expiry_date"),
            (String) body.get("version"),
            body.containsKey("inherit_permissions") ? (Boolean) body.get("inherit_permissions") : null
        );
        return ApiResponse.success(meta);
    }

    /** 查询文档列表 — 指定 kb_id 时查该 KB，否则查用户所在 Space 的所有 KB */
    @GetMapping
    public ApiResponse<Map<String, Object>> list(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int pageSize,
        @RequestParam(required = false) String status,
        @RequestParam(value = "kb_id", defaultValue = "") String kbId,
        Authentication auth
    ) {
        String token = (String) auth.getCredentials();
        String spaceId = jwtUtil.extractSpaceId(token);

        Page<DocumentMeta> result;
        if (kbId.isBlank()) {
            result = documentQueryService.listBySpace(spaceId, status, page, pageSize);
        } else {
            result = documentQueryService.listByKb(kbId, status, page, pageSize);
        }
        return ApiResponse.success(Map.of(
            "items", result.getContent(),
            "total", result.getTotalElements(),
            "page", page,
            "page_size", pageSize
        ));
    }

    @GetMapping("/{docId}")
    public ApiResponse<DocumentMeta> getById(@PathVariable String docId) {
        return ApiResponse.success(documentQueryService.getById(docId));
    }

    /** 删除文档 — 有删除权限直接删，否则创建审批 */
    @DeleteMapping("/{docId}")
    public ApiResponse<Map<String, Object>> delete(@PathVariable String docId, Authentication auth) {
        String userId = auth.getName();
        DocumentMeta doc = documentQueryService.getById(docId);
        String spaceId = doc.getSpaceId();
        String kbId = doc.getKbId();

        if (permissionService.hasPermission(userId, spaceId, kbId, "kb.delete")) {
            documentTrashService.softDelete(docId);
            return ApiResponse.success(Map.of("action", "deleted"));
        } else {
            documentApprovalService.requestDelete(docId, userId);
            return ApiResponse.success(Map.of("action", "pending_approval",
                "message", "删除请求已提交，待管理员审批"));
        }
    }

    /** 更新文档 — 有写权限直接替换，否则创建审批 */
    @PutMapping("/{docId}")
    public ApiResponse<Map<String, Object>> update(
        @PathVariable String docId,
        @RequestParam("file") MultipartFile file,
        Authentication auth
    ) {
        String userId = auth.getName();
        DocumentMeta doc = documentQueryService.getById(docId);
        String spaceId = doc.getSpaceId();
        String kbId = doc.getKbId();

        if (permissionService.hasPermission(userId, spaceId, kbId, "kb.write")) {
            documentService.adminUpdate(docId, file, userId);
            return ApiResponse.success(Map.of("action", "updated"));
        } else {
            documentService.requestUpdate(docId, file, userId);
            return ApiResponse.success(Map.of("action", "pending_approval",
                "message", "更新请求已提交，待管理员审批"));
        }
    }

    /** 恢复软删除的文档 */
    @PostMapping("/{docId}/restore")
    @RequireSpaceAdmin
    public ApiResponse<Void> restore(@PathVariable String docId) {
        documentTrashService.restore(docId);
        return ApiResponse.success();
    }

    /** 永久删除文档 */
    @DeleteMapping("/{docId}/permanent")
    @RequireSpaceAdmin
    public ApiResponse<Void> permanentDelete(@PathVariable String docId) {
        documentTrashService.permanentDelete(docId);
        return ApiResponse.success();
    }

    /** 批量软删除 — 逐文档权鉴，逻辑与单文档完全一致 */
    @DeleteMapping("/batch")
    public ApiResponse<Map<String, Object>> batchDelete(
        @RequestBody List<String> docIds, Authentication auth
    ) {
        String userId = auth.getName();
        java.util.List<String> deleted = new java.util.ArrayList<>();
        java.util.List<Map<String, String>> pendingApproval = new java.util.ArrayList<>();

        for (String docId : docIds) {
            DocumentMeta doc = documentQueryService.getById(docId);
            String spaceId = doc.getSpaceId();
            String kbId = doc.getKbId();

            if (permissionService.hasPermission(userId, spaceId, kbId, "kb.delete")) {
                documentTrashService.softDelete(docId);
                deleted.add(docId);
            } else {
                documentApprovalService.requestDelete(docId, userId);
                pendingApproval.add(Map.of("docId", docId,
                    "message", "删除请求已提交，待管理员审批"));
            }
        }

        return ApiResponse.success(Map.of(
            "deleted", deleted,
            "pending_approval", pendingApproval
        ));
    }

    /** 批量永久删除 — admin 专属 */
    @DeleteMapping("/batch/permanent")
    @RequireSpaceAdmin
    public ApiResponse<Map<String, Object>> batchPermanentDelete(
        @RequestBody List<String> docIds
    ) {
        int success = 0;
        java.util.List<Map<String, String>> failed = new java.util.ArrayList<>();

        for (String docId : docIds) {
            try {
                documentTrashService.permanentDelete(docId);
                success++;
            } catch (Exception e) {
                failed.add(Map.of("docId", docId, "reason", e.getMessage()));
            }
        }

        return ApiResponse.success(Map.of("deleted", success, "failed", failed));
    }

    // ---- 文件下载/预览 ----

    @GetMapping("/{docId}/file")
    public ResponseEntity<InputStreamResource> downloadFile(
            @PathVariable String docId,
            HttpServletRequest request) {

        String jwt = request.getParameter("token");
        if (jwt == null || jwt.isBlank()) {
            String authHeader = request.getHeader("Authorization");
            jwt = jwtUtil.extractBearerToken(authHeader);
        }
        if (jwt == null || !jwtUtil.isTokenValid(jwt)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        // 验证用户是文档所属 Space 的成员（v4 解耦：spaceId 冗余在 DocumentMeta 上）
        String userId = jwtUtil.extractUserId(jwt);
        DocumentMeta meta = documentQueryService.getById(docId);
        permissionService.requireSpaceMember(meta.getSpaceId(), userId);

        InputStream stream = minioStorageService.getFile(meta.getFilePath());

        String contentType = MIME_MAP.getOrDefault(meta.getFileType(), "application/octet-stream");
        ContentDisposition disposition = INLINE_TYPES.contains(meta.getFileType())
            ? ContentDisposition.inline().filename(meta.getFilename()).build()
            : ContentDisposition.attachment().filename(meta.getFilename()).build();

        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(contentType))
            .contentLength(meta.getFileSize())
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .body(new InputStreamResource(stream));
    }

    // ---- 审批 ----

    @GetMapping("/approvals")
    @RequireSpaceAdmin
    public ApiResponse<List<ApprovalItem>> pendingApprovals(
            @RequestParam(value = "kb_id", defaultValue = "") String kbId, Authentication auth) {
        if (kbId.isBlank()) {
            return ApiResponse.success(List.of());
        }
        return ApiResponse.success(documentApprovalService.pendingApprovals(kbId));
    }

    @PostMapping("/approvals/{approvalId}/approve")
    @RequireSpaceAdmin
    public ApiResponse<Void> approve(@PathVariable String approvalId, Authentication auth) {
        documentApprovalService.approve(approvalId, auth.getName());
        return ApiResponse.success();
    }

    @PostMapping("/approvals/{approvalId}/reject")
    @RequireSpaceAdmin
    public ApiResponse<Void> reject(@PathVariable String approvalId,
                                     @RequestBody Map<String, String> body,
                                     Authentication auth) {
        String comment = body.getOrDefault("comment", "");
        documentApprovalService.reject(approvalId, auth.getName(), comment);
        return ApiResponse.success();
    }
}
