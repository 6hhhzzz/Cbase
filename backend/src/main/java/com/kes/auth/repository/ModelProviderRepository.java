package com.kes.auth.repository;

import com.kes.auth.model.ModelProviderEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

public interface ModelProviderRepository extends JpaRepository<ModelProviderEntity, String> {
    Optional<ModelProviderEntity> findByName(String name);
    List<ModelProviderEntity> findByIsEnabledTrue();
}
