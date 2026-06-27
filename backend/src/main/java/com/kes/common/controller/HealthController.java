package com.kes.common.controller;

import com.kes.common.model.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 健康检查端点 — 供 Docker HEALTHCHECK 和 K8s Readiness/Liveness 探针使用。
 */
@RestController
public class HealthController {

    @GetMapping("/api/health")
    public ApiResponse<String> health() {
        return ApiResponse.success("ok");
    }
}
