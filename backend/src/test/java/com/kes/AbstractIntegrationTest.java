package com.kes;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * 集成测试基类 — 使用 TestContainers 启动真实 PostgreSQL (pgvector) 数据库。
 *
 * <p>子类自动获得:
 * <ul>
 *   <li>一个隔离的 PostgreSQL 16 + pgvector 容器</li>
 *   <li>{@code @SpringBootTest} 完整应用上下文</li>
 *   <li>test profile（禁用 Redis/RabbitMQ/MQ 自动配置）</li>
 * </ul>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Testcontainers
public abstract class AbstractIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("pgvector/pgvector:pg16")
        .withDatabaseName("kes")
        .withUsername("kes")
        .withPassword("kes123");

    @DynamicPropertySource
    static void datasourceConfig(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () ->
            "jdbc:postgresql://" + postgres.getHost() + ":" + postgres.getMappedPort(5432)
            + "/kes?stringtype=unspecified");
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
