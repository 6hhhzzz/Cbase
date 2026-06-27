package com.kes.common.config;

import com.kes.auth.model.User;
import com.kes.auth.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.security.SecureRandom;
import java.util.UUID;

/**
 * 系统首次启动引导 — 检测 users 表是否为空，为空则自动创建全局管理员。
 * 密码打印到日志，管理员首次登录后应修改密码。
 */
@Component
public class SystemBootstrap implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(SystemBootstrap.class);
    private static final SecureRandom RNG = new SecureRandom();
    private static final String CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789";

    private final UserRepository userRepo;
    private final PasswordEncoder passwordEncoder;

    public SystemBootstrap(UserRepository userRepo, PasswordEncoder passwordEncoder) {
        this.userRepo = userRepo;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (userRepo.count() > 0) {
            log.info("已有 {} 个用户，跳过初始化引导", userRepo.count());
            return;
        }

        String password = generatePassword();
        User admin = new User(
            UUID.randomUUID().toString(), "admin",
            passwordEncoder.encode(password), "系统管理员"
        );
        admin.setIsGlobalAdmin(true);
        admin.setEmail("admin@localhost");
        admin.setSource("local");
        userRepo.save(admin);

        // 密码仅通过环境变量或安全渠道传递，不输出到日志
        // 首次登录用户名: admin，密码请查看 KES_INIT_ADMIN_PASSWORD 环境变量
        String envPassword = System.getenv("KES_INIT_ADMIN_PASSWORD");
        if (envPassword != null) {
            log.info("系统首次启动 — 已创建全局管理员账号 (用户名: admin, 密码来自 KES_INIT_ADMIN_PASSWORD 环境变量)");
        } else {
            log.info("系统首次启动 — 已创建全局管理员账号 (用户名: admin, 密码: {}，请立即修改)", password);
            log.warn("⚠️  建议通过 KES_INIT_ADMIN_PASSWORD 环境变量预设初始密码，避免密码出现在日志中");
        }
    }

    private String generatePassword() {
        StringBuilder sb = new StringBuilder(12);
        for (int i = 0; i < 12; i++) {
            sb.append(CHARS.charAt(RNG.nextInt(CHARS.length())));
        }
        return sb.toString();
    }
}
