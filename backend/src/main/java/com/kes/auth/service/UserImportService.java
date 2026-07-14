package com.kes.auth.service;

import com.kes.auth.model.BatchImportResult;
import com.kes.auth.model.User;
import com.kes.auth.repository.UserRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.service.AuditLogger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 用户批量导入服务（全局管理员）。
 * 处理 CSV 批量导入用户的操作。
 *
 * <p>从 {@link AdminService} 拆分而来，仅限全局超级管理员调用。
 *
 * <p>依赖：{@link PermissionService}（权限校验）、{@link AuditLogger}（操作记录）
 */
@Service
public class UserImportService {

    private static final Logger log = LoggerFactory.getLogger(UserImportService.class);
    private static final String GLOBAL = "00000000-0000-0000-0000-000000000000";

    private static final SecureRandom RNG = new SecureRandom();
    private static final String PASSWORD_CHARS =
        "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789@#$%";

    private final UserRepository userRepo;
    private final AuditLogger auditLogger;
    private final PasswordEncoder passwordEncoder;
    private final GroupService groupService;
    private final PermissionService permService;

    public UserImportService(UserRepository userRepo,
                             AuditLogger auditLogger,
                             PasswordEncoder passwordEncoder,
                             GroupService groupService,
                             PermissionService permService) {
        this.userRepo = userRepo;
        this.auditLogger = auditLogger;
        this.passwordEncoder = passwordEncoder;
        this.groupService = groupService;
        this.permService = permService;
    }

    /** 批量导入用户（CSV） */
    @Transactional
    public BatchImportResult batchImportUsers(String operatorId, MultipartFile file) {
        permService.requireGlobalAdmin(operatorId);

        List<BatchImportResult.ImportError> errors = new ArrayList<>();
        int success = 0;
        int total = 0;

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(file.getInputStream(), StandardCharsets.UTF_8))) {

            // 解析表头
            String headerLine = reader.readLine();
            if (headerLine == null) {
                throw new BusinessException(ErrorCode.CSV_EMPTY);
            }
            List<String> headers = parseCsvLine(headerLine);
            int idxUsername = headers.indexOf("username");
            int idxDisplayName = headers.indexOf("display_name");
            int idxEmail = headers.indexOf("email");
            int idxDepartmentPath = headers.indexOf("department_path");  // ★ v9: 嵌套组路径
            int idxGroups = headers.indexOf("groups");                   // ★ v9: 多组（|分隔）
            int idxGroup = headers.indexOf("group_name");                // 兼容旧格式
            int idxPassword = headers.indexOf("password");               // 企业同步：明文密码列

            if (idxUsername < 0 || idxDisplayName < 0) {
                throw new BusinessException(ErrorCode.CSV_MISSING_COLUMN,
                    "CSV 表头必须包含 username 和 display_name 列");
            }

            // 预加载组映射（name → groupId），避免每行查库
            Map<String, String> groupCache = new HashMap<>();

            // 逐行解析
            String line;
            int rowNum = 1;
            while ((line = reader.readLine()) != null) {
                rowNum++;
                total++;
                List<String> cols = parseCsvLine(line);

                String username = cols.size() > idxUsername ? cols.get(idxUsername).trim() : "";
                String displayName = cols.size() > idxDisplayName ? cols.get(idxDisplayName).trim() : "";
                String email = idxEmail >= 0 && cols.size() > idxEmail ? cols.get(idxEmail).trim() : "";
                String departmentPath = idxDepartmentPath >= 0 && cols.size() > idxDepartmentPath
                    ? cols.get(idxDepartmentPath).trim() : "";
                String groupsStr = idxGroups >= 0 && cols.size() > idxGroups
                    ? cols.get(idxGroups).trim() : "";
                String groupName = idxGroup >= 0 && cols.size() > idxGroup
                    ? cols.get(idxGroup).trim() : "";
                String password = idxPassword >= 0 && cols.size() > idxPassword
                    ? cols.get(idxPassword).trim() : "";

                // 校验
                if (username.isEmpty()) {
                    errors.add(new BatchImportResult.ImportError(rowNum, "", "用户名为空"));
                    continue;
                }
                if (username.length() < 3 || username.length() > 32) {
                    errors.add(new BatchImportResult.ImportError(rowNum, username, "用户名长度需 3-32 字符"));
                    continue;
                }
                if (displayName.isEmpty()) {
                    errors.add(new BatchImportResult.ImportError(rowNum, username, "显示名称为空"));
                    continue;
                }
                if (userRepo.existsByUsername(username)) {
                    errors.add(new BatchImportResult.ImportError(rowNum, username, "用户名已存在"));
                    continue;
                }

                // 创建用户
                try {
                    String userId = UUID.randomUUID().toString();
                    // ★ 企业同步：CSV 有密码则用企业密码，否则随机生成
                    boolean hasPassword = !password.isEmpty();
                    String rawPassword = hasPassword ? password : generateRandomPassword();
                    User user = new User(userId, username,
                        passwordEncoder.encode(rawPassword), displayName);
                    if (!email.isEmpty()) user.setEmail(email);
                    user.setSource("import");
                    // 企业自带密码 → 无需强制改密；随机密码 → 首次登录必须改密
                    user.setMustChangePassword(!hasPassword);
                    userRepo.save(user);

                    // ★ v9: 嵌套组路径 — "公司/技术中心/后端组"
                    if (!departmentPath.isEmpty()) {
                        try {
                            String leafGroupId = groupService.findOrCreateGroupPath(
                                departmentPath, operatorId);
                            groupService.addMember(leafGroupId, userId);
                        } catch (Exception e) {
                            errors.add(new BatchImportResult.ImportError(
                                rowNum, username, "组路径处理失败: " + e.getMessage()));
                        }
                    }

                    // ★ v9: 多组归属（| 分隔）— "引擎组|核心组|全员公告组"
                    if (!groupsStr.isEmpty()) {
                        for (String gName : groupsStr.split("\\|")) {
                            gName = gName.trim();
                            if (gName.isEmpty()) continue;
                            try {
                                String gid = groupCache.get(gName);
                                if (gid == null) {
                                    var grp = groupService.findByName(gName);
                                    if (grp.isPresent()) {
                                        gid = grp.get().getId();
                                        groupCache.put(gName, gid);
                                    }
                                }
                                if (gid != null) {
                                    groupService.addMember(gid, userId);
                                } else {
                                    errors.add(new BatchImportResult.ImportError(
                                        rowNum, username, "组不存在: " + gName));
                                }
                            } catch (Exception e) {
                                errors.add(new BatchImportResult.ImportError(
                                    rowNum, username, "加入组失败 '" + gName + "': " + e.getMessage()));
                            }
                        }
                    }

                    // 兼容旧格式：单个 group_name
                    if (!groupName.isEmpty()) {
                        String gid = groupCache.get(groupName);
                        if (gid == null) {
                            var grp = groupService.findByName(groupName);
                            if (grp.isPresent()) {
                                gid = grp.get().getId();
                                groupCache.put(groupName, gid);
                            }
                        }
                        if (gid != null) {
                            groupService.addMember(gid, userId);
                        }
                    }

                    success++;
                } catch (Exception e) {
                    errors.add(new BatchImportResult.ImportError(
                        rowNum, username, "创建失败: " + e.getMessage()));
                }
            }
        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            throw new BusinessException(ErrorCode.CSV_PARSE_FAILED, "CSV 解析失败: " + e.getMessage());
        }

        int failed = total - success;
        auditLogger.log(operatorId, GLOBAL, "user.batch_import", "user", GLOBAL,
            "batch:" + success + "/" + total, "{\"total\":" + total + ",\"success\":" + success + ",\"failed\":" + failed + "}");
        log.info("批量导入用户完成: operator={}, total={}, success={}, failed={}",
            operatorId, total, success, failed);

        return new BatchImportResult(total, success, failed, errors);
    }

    // ================================================================
    // 私有辅助
    // ================================================================

    private String generateRandomPassword() {
        StringBuilder sb = new StringBuilder(16);
        for (int i = 0; i < 16; i++) {
            sb.append(PASSWORD_CHARS.charAt(RNG.nextInt(PASSWORD_CHARS.length())));
        }
        return sb.toString();
    }

    /** 简易 CSV 行解析，支持双引号包裹的字段 */
    private List<String> parseCsvLine(String line) {
        List<String> result = new ArrayList<>();
        boolean inQuotes = false;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (inQuotes) {
                if (c == '"') {
                    if (i + 1 < line.length() && line.charAt(i + 1) == '"') {
                        sb.append('"');
                        i++;
                    } else {
                        inQuotes = false;
                    }
                } else {
                    sb.append(c);
                }
            } else {
                if (c == '"') {
                    inQuotes = true;
                } else if (c == ',') {
                    result.add(sb.toString().trim());
                    sb.setLength(0);
                } else {
                    sb.append(c);
                }
            }
        }
        result.add(sb.toString().trim());
        return result;
    }
}
