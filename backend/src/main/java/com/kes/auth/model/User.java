package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 用户实体 — v7 用户管理增强 (email/status/source/mustChangePassword)。
 */
@Entity
@Table(name = "users")
public class User {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "is_global_admin")
    private Boolean isGlobalAdmin = false;

    @Column(unique = true, nullable = false, length = 32)
    private String username;

    @Column(nullable = false, length = 255)
    private String password;  // BCrypt 加密

    @Column(nullable = false, length = 64)
    private String displayName;

    @Column(length = 255)
    private String email;

    @Column(length = 16)
    private String status = "active";  // active | disabled

    @Column(length = 32)
    private String source = "local";   // local | import | oidc

    @Column(name = "must_change_password")
    private Boolean mustChangePassword = false;

    @Column(updatable = false)
    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    // ---- 构造函数 ----

    public User() {}

    public User(String id, String username, String password, String displayName) {
        this.id = id;
        this.username = username;
        this.password = password;
        this.displayName = displayName;
    }

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) { this.displayName = displayName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }

    public Boolean getMustChangePassword() { return mustChangePassword; }
    public void setMustChangePassword(Boolean mustChangePassword) { this.mustChangePassword = mustChangePassword; }

    public Boolean getIsGlobalAdmin() { return isGlobalAdmin; }
    public void setIsGlobalAdmin(Boolean isGlobalAdmin) { this.isGlobalAdmin = isGlobalAdmin; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
