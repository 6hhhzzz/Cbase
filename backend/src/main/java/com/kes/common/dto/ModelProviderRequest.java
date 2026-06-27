package com.kes.common.dto;

import jakarta.validation.constraints.NotBlank;

public class ModelProviderRequest {
    @NotBlank private String name;
    @NotBlank private String type;
    @NotBlank private String baseUrl;
    private String apiKeyEnv;
    private boolean isEnabled = true;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    public String getApiKeyEnv() { return apiKeyEnv; }
    public void setApiKeyEnv(String apiKeyEnv) { this.apiKeyEnv = apiKeyEnv; }
    public boolean getIsEnabled() { return isEnabled; }
    public void setIsEnabled(boolean isEnabled) { this.isEnabled = isEnabled; }
}
