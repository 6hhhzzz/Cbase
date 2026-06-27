package com.kes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

/**
 * 企业知识助手 Java Backend 主入口 — v3 Space/KB RBAC。
 */
@SpringBootApplication
@EnableJpaRepositories(basePackages = "com.kes")    // 明示 JPA 仓库范围，避免 Redis 扫描噪点
public class KesApplication {

    public static void main(String[] args) {
        SpringApplication.run(KesApplication.class, args);
    }
}
