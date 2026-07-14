package com.kes;

import io.minio.MinioClient;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * 集成测试基类 — 使用 TestContainers 启动真实 PostgreSQL (pgvector) + Redis。
 *
 * <p>子类自动获得:
 * <ul>
 *   <li>一个隔离的 PostgreSQL 16 + pgvector 容器（承载业务数据）</li>
 *   <li>一个隔离的 Redis 7 容器（KbPermissionCache kb_ids 权限缓存依赖）</li>
 *   <li>{@code @SpringBootTest} 完整应用上下文</li>
 *   <li>MinIO / RabbitMQ 被 mock — 这些纯 I/O 边界不是集成测试的被测目标</li>
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

    @Container
    static GenericContainer<?> redis = new GenericContainer<>("redis:7-alpine")
        .withExposedPorts(6379);

    /** 文件存储边界 — mock 掉，避免 MinioStorageService 启动期连接真实 MinIO。 */
    @MockBean
    MinioClient minioClient;

    /** 消息发布边界 — mock 掉，满足 DocumentService 等对 RabbitTemplate 的构造注入。 */
    @MockBean
    RabbitTemplate rabbitTemplate;

    @DynamicPropertySource
    static void containerConfig(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () ->
            "jdbc:postgresql://" + postgres.getHost() + ":" + postgres.getMappedPort(5432)
            + "/kes?stringtype=unspecified");
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);

        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port", () -> redis.getMappedPort(6379));
    }
}
