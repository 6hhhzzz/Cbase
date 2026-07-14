package com.kes.auth.controller;

import com.kes.AbstractIntegrationTest;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * AuthController 集成测试 — 完整认证链路。
 * 使用真实 PostgreSQL + MockMvc 测试全栈 Spring MVC。
 */
class AuthControllerIT extends AbstractIntegrationTest {

    @Autowired
    private WebApplicationContext ctx;

    @Autowired
    private ObjectMapper objectMapper;

    private MockMvc mvc;
    private String refreshToken;
    private String contextToken;
    private String spaceId;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(ctx).build();
    }

    @Test
    @Order(1)
    void fullAuthFlow() throws Exception {
        // 1. 注册
        var registerBody = Map.of("username", "testuser", "password", "password123", "display_name", "测试用户");
        var registerRes = mvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(registerBody)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value(0))
            .andExpect(jsonPath("$.data.id").isNotEmpty())
            .andReturn();
        refreshToken = extractToken(registerRes, "refresh_token");
        spaceId = extractNested(registerRes, "spaces[0].spaceId");

        // 2. 登录
        var loginBody = Map.of("username", "testuser", "password", "password123");
        var loginRes = mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(loginBody)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.refresh_token").isNotEmpty())
            .andReturn();
        refreshToken = extractToken(loginRes, "refresh_token");

        // 3. 刷新 Token
        var refreshBody = Map.of("refresh_token", refreshToken);
        var refreshRes = mvc.perform(post("/api/auth/refresh")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(refreshBody)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.refresh_token").isNotEmpty())
            .andReturn();
        refreshToken = extractToken(refreshRes, "refresh_token");

        // 4. 获取 Space 列表
        mvc.perform(get("/api/auth/spaces")
                .header("Authorization", "Bearer " + refreshToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data").isArray())
            .andExpect(jsonPath("$.data[0].spaceId").isNotEmpty());

        // 5. 切换 Space — 签发 context_token
        var switchBody = Map.of("space_id", spaceId);
        var switchRes = mvc.perform(post("/api/auth/switch-space")
                .header("Authorization", "Bearer " + refreshToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(switchBody)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.context_token").isNotEmpty())
            .andReturn();
        contextToken = extractToken(switchRes, "context_token");

        // 6. 获取可访问 KB 列表
        mvc.perform(get("/api/auth/accessible-kbs")
                .header("Authorization", "Bearer " + contextToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data").isArray());
    }

    @Test
    void loginWithWrongPassword_returnsError() throws Exception {
        // 先注册
        var registerBody = Map.of("username", "wrongpw", "password", "correctpw", "display_name", "用户");
        mvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(registerBody)))
            .andExpect(status().isOk());

        // 用错误密码登录
        var loginBody = Map.of("username", "wrongpw", "password", "wrongpassword");
        mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(loginBody)))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error_code").value("AUTH_BAD_CREDENTIALS"));
    }

    @Test
    void registerDuplicateUsername_returnsError() throws Exception {
        var body = Map.of("username", "dup", "password", "pass123456", "display_name", "重复");
        mvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(body)))
            .andExpect(status().isOk());

        mvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(body)))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.error_code").value("AUTH_USERNAME_EXISTS"));
    }

    // ---- helpers ----

    private String extractToken(org.springframework.test.web.servlet.MvcResult result, String key) throws Exception {
        var node = objectMapper.readTree(result.getResponse().getContentAsString());
        return node.path("data").path(key).asText();
    }

    private String extractNested(org.springframework.test.web.servlet.MvcResult result, String jsonPath) throws Exception {
        // Simple support for "spaces[0].spaceId"
        var node = objectMapper.readTree(result.getResponse().getContentAsString());
        var data = node.path("data");
        if (data.isArray() && !data.isEmpty()) {
            return data.get(0).path("spaceId").asText();
        }
        return "";
    }
}
