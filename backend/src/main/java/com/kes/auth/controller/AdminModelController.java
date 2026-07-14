package com.kes.auth.controller;

import com.kes.auth.service.AdminModelService;
import com.kes.common.annotation.RequireGlobalAdmin;
import com.kes.common.dto.ModelAssignmentRequest;
import com.kes.common.dto.ModelConfigRequest;
import com.kes.common.dto.ModelProviderRequest;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.model.ApiResponse;
import com.kes.rag.client.AiServiceClient;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 模型配置管理 Controller — v6 模型配置中心。
 * 所有端点需要 @RequireGlobalAdmin 权限。
 *
 * Python AI 服务通过 GET /api/admin/models/active 获取全量配置。
 * 配置变更后自动递增 config_version（热重载信号）。
 */
@RestController
@RequestMapping("/api/admin/models")
public class AdminModelController {

    private final AdminModelService service;
    private final AiServiceClient aiClient;

    public AdminModelController(AdminModelService service, AiServiceClient aiClient) {
        this.service = service;
        this.aiClient = aiClient;
    }

    // ---- Provider ----

    @GetMapping("/providers")
    @RequireGlobalAdmin
    public ApiResponse<?> listProviders() {
        return ApiResponse.success(service.listProviders());
    }

    @PostMapping("/providers")
    @RequireGlobalAdmin
    public ApiResponse<?> createProvider(@Valid @RequestBody ModelProviderRequest req) {
        return ApiResponse.success(service.createProvider(req));
    }

    @PutMapping("/providers/{id}")
    @RequireGlobalAdmin
    public ApiResponse<?> updateProvider(@PathVariable String id,
                                          @Valid @RequestBody ModelProviderRequest req) {
        return ApiResponse.success(service.updateProvider(id, req));
    }

    @DeleteMapping("/providers/{id}")
    @RequireGlobalAdmin
    public ApiResponse<?> deleteProvider(@PathVariable String id) {
        service.deleteProvider(id);
        return ApiResponse.success(null);
    }

    // ---- Model Config ----

    @GetMapping("/configs")
    @RequireGlobalAdmin
    public ApiResponse<?> listConfigs(@RequestParam(required = false) String providerId) {
        return ApiResponse.success(service.listConfigs(providerId));
    }

    @PostMapping("/configs")
    @RequireGlobalAdmin
    public ApiResponse<?> createConfig(@Valid @RequestBody ModelConfigRequest req) {
        return ApiResponse.success(service.createConfig(req));
    }

    @PutMapping("/configs/{id}")
    @RequireGlobalAdmin
    public ApiResponse<?> updateConfig(@PathVariable String id,
                                        @Valid @RequestBody ModelConfigRequest req) {
        return ApiResponse.success(service.updateConfig(id, req));
    }

    @DeleteMapping("/configs/{id}")
    @RequireGlobalAdmin
    public ApiResponse<?> deleteConfig(@PathVariable String id) {
        service.deleteConfig(id);
        return ApiResponse.success(null);
    }

    // ---- Assignment ----

    @GetMapping("/assignments")
    @RequireGlobalAdmin
    public ApiResponse<?> getAssignments() {
        return ApiResponse.success(service.getAssignments());
    }

    @PutMapping("/assignments")
    @RequireGlobalAdmin
    public ApiResponse<?> updateAssignments(@RequestBody ModelAssignmentRequest req) {
        return ApiResponse.success(service.updateAssignments(req));
    }

    // ---- 模型发现 + 连通性测试（代理到 Python AI 服务） ----

    @PostMapping("/discover/{providerId}")
    @RequireGlobalAdmin
    public ApiResponse<?> discoverModels(@PathVariable String providerId) {
        var provider = ((Map<String, Object>) service.listProviders().stream()
                .filter(p -> providerId.equals(p.get("id")) || providerId.equals(p.get("name")))
                .findFirst().orElseThrow(() ->
                        new BusinessException(ErrorCode.PARAM_INVALID, "Provider 不存在")));
        String apiKey = service.resolveApiKey((String) provider.get("api_key_env"));
        Map<String, Object> req = Map.of(
                "provider_type", provider.get("type"),
                "base_url", provider.get("base_url"),
                "api_key", apiKey
        );
        return ApiResponse.success(aiClient.discoverModels(req).block());
    }

    @PostMapping("/test/{providerId}")
    @RequireGlobalAdmin
    public ApiResponse<?> testConnection(@PathVariable String providerId) {
        var provider = ((Map<String, Object>) service.listProviders().stream()
                .filter(p -> providerId.equals(p.get("id")) || providerId.equals(p.get("name")))
                .findFirst().orElseThrow(() ->
                        new BusinessException(ErrorCode.PARAM_INVALID, "Provider 不存在")));
        String apiKey = service.resolveApiKey((String) provider.get("api_key_env"));
        Map<String, Object> req = Map.of(
                "provider_type", provider.get("type"),
                "base_url", provider.get("base_url"),
                "api_key", apiKey
        );
        return ApiResponse.success(aiClient.testModelConnection(req).block());
    }

    // ---- v12: 配置文件读写（代理到 Python） ----

    @GetMapping("/config")
    @RequireGlobalAdmin
    public ApiResponse<?> getModelsConfig() {
        return ApiResponse.success(aiClient.getModelsConfig().block());
    }

    @PutMapping("/config")
    @RequireGlobalAdmin
    public ApiResponse<?> updateModelsConfig(@RequestBody Map<String, String> body) {
        String yamlContent = body.getOrDefault("yaml_content", "");
        if (yamlContent.isBlank()) {
            throw new BusinessException(ErrorCode.PARAM_INVALID, "yaml_content 不能为空");
        }
        return ApiResponse.success(aiClient.updateModelsConfig(yamlContent).block());
    }

    // ---- Python 用：全量激活配置 + 版本号 ----

    @GetMapping("/active")
    public ApiResponse<?> getActiveConfigs() {
        // 不做 @RequireGlobalAdmin — Python 服务用，通过内网调用
        return ApiResponse.success(service.getActiveConfigs());
    }

    @GetMapping("/version")
    public ApiResponse<?> getConfigVersion() {
        return ApiResponse.success(Map.of("version", service.getConfigVersion()));
    }
}
