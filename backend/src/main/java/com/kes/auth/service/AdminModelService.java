package com.kes.auth.service;

import com.kes.auth.model.ModelAssignmentEntity;
import com.kes.auth.model.ModelConfigEntity;
import com.kes.auth.model.ModelProviderEntity;
import com.kes.auth.repository.ModelAssignmentRepository;
import com.kes.auth.repository.ModelConfigRepository;
import com.kes.auth.repository.ModelProviderRepository;
import com.kes.common.dto.ModelAssignmentRequest;
import com.kes.common.dto.ModelConfigRequest;
import com.kes.common.dto.ModelProviderRequest;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 模型配置管理服务 — v6 模型配置中心。
 *
 * 职责：
 *   - Provider/Model/Assignment 的 CRUD
 *   - API Key 脱敏（只返回环境变量名，绝不返回实际值）
 *   - 配置版本号递增（热重载信号）
 */
@Service
public class AdminModelService {

    private static final Logger log = LoggerFactory.getLogger(AdminModelService.class);

    private final ModelProviderRepository providerRepo;
    private final ModelConfigRepository configRepo;
    private final ModelAssignmentRepository assignmentRepo;
    private final JdbcTemplate jdbc;

    public AdminModelService(ModelProviderRepository providerRepo,
                              ModelConfigRepository configRepo,
                              ModelAssignmentRepository assignmentRepo,
                              JdbcTemplate jdbc) {
        this.providerRepo = providerRepo;
        this.configRepo = configRepo;
        this.assignmentRepo = assignmentRepo;
        this.jdbc = jdbc;
    }

    // ---- Provider CRUD ----

    public List<Map<String, Object>> listProviders() {
        return providerRepo.findAll().stream()
                .map(this::toProviderMap)
                .collect(Collectors.toList());
    }

    @Transactional
    public Map<String, Object> createProvider(ModelProviderRequest req) {
        validateProvider(req);
        ModelProviderEntity entity = new ModelProviderEntity(
                UUID.randomUUID().toString(), req.getName(), req.getType(),
                req.getBaseUrl(), req.getApiKeyEnv(), req.getIsEnabled()
        );
        try {
            providerRepo.save(entity);
        } catch (DataIntegrityViolationException e) {
            throw new BusinessException(ErrorCode.MODEL_NAME_CONFLICT,
                    "Provider 名称已存在: " + req.getName());
        }
        incrementConfigVersion();
        log.info("创建 Provider: {} (type={})", req.getName(), req.getType());
        return toProviderMap(entity);
    }

    @Transactional
    public Map<String, Object> updateProvider(String id, ModelProviderRequest req) {
        ModelProviderEntity entity = providerRepo.findById(id)
                .orElseThrow(() -> new BusinessException(ErrorCode.MODEL_PROVIDER_NOT_FOUND));
        entity.setName(req.getName());
        entity.setType(req.getType());
        entity.setBaseUrl(req.getBaseUrl());
        entity.setApiKeyEnv(req.getApiKeyEnv());
        entity.setIsEnabled(req.getIsEnabled());
        providerRepo.save(entity);
        incrementConfigVersion();
        return toProviderMap(entity);
    }

    @Transactional
    public void deleteProvider(String id) {
        if (!providerRepo.existsById(id)) {
            throw new BusinessException(ErrorCode.MODEL_PROVIDER_NOT_FOUND);
        }
        providerRepo.deleteById(id);
        incrementConfigVersion();
    }

    // ---- Model CRUD ----

    public List<Map<String, Object>> listConfigs(String providerId) {
        List<ModelConfigEntity> list = (providerId != null && !providerId.isEmpty())
                ? configRepo.findByProviderId(providerId)
                : configRepo.findAll();
        return list.stream()
                .map(this::toConfigMap)
                .collect(Collectors.toList());
    }

    @Transactional
    public Map<String, Object> createConfig(ModelConfigRequest req) {
        ModelProviderEntity provider = providerRepo.findById(req.getProviderId())
                .orElseThrow(() -> new BusinessException(ErrorCode.MODEL_PROVIDER_NOT_FOUND));
        ModelConfigEntity entity = new ModelConfigEntity(
                UUID.randomUUID().toString(), provider, req.getModelName(),
                req.getModelType(), req.getDimension(), req.getMaxTokens()
        );
        entity.setIsEnabled(req.getIsEnabled());
        try {
            configRepo.save(entity);
        } catch (DataIntegrityViolationException e) {
            throw new BusinessException(ErrorCode.MODEL_NAME_CONFLICT,
                    "该 Provider 下已存在同名模型: " + req.getModelName());
        }
        incrementConfigVersion();
        return toConfigMap(entity);
    }

    @Transactional
    public Map<String, Object> updateConfig(String id, ModelConfigRequest req) {
        ModelConfigEntity entity = configRepo.findById(id)
                .orElseThrow(() -> new BusinessException(ErrorCode.MODEL_CONFIG_NOT_FOUND));
        entity.setModelName(req.getModelName());
        entity.setModelType(req.getModelType());
        entity.setDimension(req.getDimension());
        entity.setMaxTokens(req.getMaxTokens());
        entity.setIsEnabled(req.getIsEnabled());
        configRepo.save(entity);
        incrementConfigVersion();
        return toConfigMap(entity);
    }

    @Transactional
    public void deleteConfig(String id) {
        if (!configRepo.existsById(id)) {
            throw new BusinessException(ErrorCode.MODEL_CONFIG_NOT_FOUND);
        }
        configRepo.deleteById(id);
        incrementConfigVersion();
    }

    // ---- Assignment ----

    public Map<String, String> getAssignments() {
        Map<String, String> result = new LinkedHashMap<>();
        for (ModelAssignmentEntity a : assignmentRepo.findAll()) {
            result.put(a.getPurpose(), a.getModel() != null ? a.getModel().getId() : null);
        }
        return result;
    }

    @Transactional
    public Map<String, String> updateAssignments(ModelAssignmentRequest req) {
        for (Map.Entry<String, String> e : req.getAssignments().entrySet()) {
            ModelAssignmentEntity assignment = assignmentRepo.findByPurpose(e.getKey())
                    .orElseGet(() -> new ModelAssignmentEntity(
                            UUID.randomUUID().toString(), e.getKey(), null));
            if (e.getValue() != null) {
                ModelConfigEntity model = configRepo.findById(e.getValue())
                        .orElseThrow(() -> new BusinessException(ErrorCode.MODEL_CONFIG_NOT_FOUND,
                                "模型不存在: " + e.getValue()));
                assignment.setModel(model);
            } else {
                assignment.setModel(null);
            }
            assignmentRepo.save(assignment);
        }
        incrementConfigVersion();
        return getAssignments();
    }

    // ---- Python 用：全量激活配置 ----

    public Map<String, Object> getActiveConfigs() {
        Map<String, Object> result = new LinkedHashMap<>();
        // Providers
        List<Map<String, Object>> providers = providerRepo.findByIsEnabledTrue().stream()
                .map(p -> {
                    Map<String, Object> m = toProviderMap(p);
                    m.put("api_key", resolveApiKey(p.getApiKeyEnv()));  // 实际 key（仅 Python 用）
                    return m;
                })
                .collect(Collectors.toList());
        result.put("providers", providers);

        // Models
        List<Map<String, Object>> models = configRepo.findAll().stream()
                .filter(ModelConfigEntity::getIsEnabled)
                .map(this::toConfigMap)
                .collect(Collectors.toList());
        result.put("models", models);

        // Assignments
        List<Map<String, Object>> assignments = assignmentRepo.findAll().stream()
                .map(a -> {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("purpose", a.getPurpose());
                    if (a.getModel() != null) {
                        m.put("model", toConfigMap(a.getModel()));
                        // 嵌入 provider 信息
                        m.put("provider", toProviderMap(a.getModel().getProvider()));
                        m.get("provider");
                    }
                    return m;
                })
                .collect(Collectors.toList());
        result.put("assignments", assignments);

        return result;
    }

    // ---- 配置版本号 ----

    public long getConfigVersion() {
        String val = jdbc.queryForObject(
                "SELECT value FROM system_config WHERE key = 'model_config_version'",
                String.class);
        return val != null ? Long.parseLong(val) : 1L;
    }

    private void incrementConfigVersion() {
        jdbc.update("UPDATE system_config SET value = ?, updated_at = NOW() WHERE key = 'model_config_version'",
                String.valueOf(System.currentTimeMillis()));
    }

    // ---- 脱敏映射 ----

    private Map<String, Object> toProviderMap(ModelProviderEntity p) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", p.getId());
        m.put("name", p.getName());
        m.put("type", p.getType());
        m.put("base_url", p.getBaseUrl());
        m.put("api_key_env", p.getApiKeyEnv());  // 只返回变量名，不返回实际值
        m.put("is_enabled", p.getIsEnabled());
        return m;
    }

    private Map<String, Object> toConfigMap(ModelConfigEntity c) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", c.getId());
        m.put("model_name", c.getModelName());
        m.put("model_type", c.getModelType());
        m.put("dimension", c.getDimension());
        m.put("max_tokens", c.getMaxTokens());
        m.put("is_enabled", c.getIsEnabled());
        if (c.getProvider() != null) {
            m.put("provider_id", c.getProvider().getId());
            m.put("provider_name", c.getProvider().getName());
        }
        return m;
    }

    // ---- 内部 ----

    private void validateProvider(ModelProviderRequest req) {
        if (req.getBaseUrl() != null && !req.getBaseUrl().startsWith("https://")
                && !req.getBaseUrl().startsWith("http://localhost")
                && !req.getBaseUrl().startsWith("http://127.0.0.1")
                && !req.getBaseUrl().equals("local")) {
            throw new BusinessException(ErrorCode.MODEL_INVALID_URL,
                    "Base URL 必须以 https:// 开头，或为 localhost/127.0.0.1");
        }
    }

    public String resolveApiKey(String envVarName) {
        if (envVarName == null || envVarName.isEmpty()) return "";
        String varName = envVarName.replace("${", "").replace("}", "");
        return System.getenv().getOrDefault(varName, "");
    }
}
