package com.kes.auth.repository;

import com.kes.auth.model.ApiKey;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface ApiKeyRepository extends JpaRepository<ApiKey, String> {

    List<ApiKey> findByUserIdOrderByCreatedAtDesc(String userId);

    Optional<ApiKey> findByKeyHash(String keyHash);

    boolean existsByUserIdAndName(String userId, String name);
}
