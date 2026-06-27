package com.kes.auth.repository;

import com.kes.auth.model.ModelConfigEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ModelConfigRepository extends JpaRepository<ModelConfigEntity, String> {
    List<ModelConfigEntity> findByProviderId(String providerId);
}
