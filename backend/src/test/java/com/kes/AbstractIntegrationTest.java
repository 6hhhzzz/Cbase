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

/**
 * 集成测试基类 — 使用 TestContainers 启动真实 PostgreSQL (pgvector) + Redis。
 *
 * <p>采用<strong>单例容器模式</strong>:容器在 {@code static} 块中手动启动一次，
 * 全 JVM 共享，跨所有 IT 类不重启（Ryuk 在 JVM 退出时清理）。
 *
 * <p>不使用 {@code @Testcontainers}/{@code @Container}——那会<em>按测试类</em>启停容器，
 * 而所有 IT 的 {@code @SpringBootTest} 配置相同、Spring 会缓存复用同一个上下文，
 * 导致后续测试类的 DataSource 指向已停止的容器（HikariPool total=0，30s 超时）。
 *
 * <p>子类自动获得:
 * <ul>
 *   <li>共享的 PostgreSQL 16 + pgvector 容器（承载业务数据）</li>
 *   <li>共享的 Redis 7 容器（KbPermissionCache kb_ids 权限缓存依赖）</li>
 *   <li>{@code @SpringBootTest} 完整应用上下文</li>
 *   <li>MinIO / RabbitMQ 被 mock — 这些纯 I/O 边界不是集成测试的被测目标</li>
 * </ul>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
public abstract class AbstractIntegrationTest {

    static final PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("pgvector/pgvector:pg16")
        .withDatabaseName("kes")
        .withUsername("kes")
        .withPassword("kes123");

    static final GenericContainer<?> redis = new GenericContainer<>("redis:7-alpine")
        .withExposedPorts(6379);

    static {
        postgres.start();
        redis.start();
    }

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
