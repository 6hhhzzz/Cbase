package com.kes.document.service;

import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import io.minio.*;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.InputStream;

@Service
public class MinioStorageService {

    private static final Logger log = LoggerFactory.getLogger(MinioStorageService.class);

    private final MinioClient minioClient;
    private final String bucket;

    public MinioStorageService(MinioClient minioClient, String minioBucket) {
        this.minioClient = minioClient;
        this.bucket = minioBucket;
    }

    @PostConstruct
    public void ensureBucketExists() {
        try {
            boolean found = minioClient.bucketExists(
                    BucketExistsArgs.builder().bucket(bucket).build());
            if (!found) {
                minioClient.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
                log.info("MinIO bucket 已创建: {}", bucket);
            } else {
                log.info("MinIO bucket 已存在: {}", bucket);
            }
        } catch (Exception e) {
            log.error("MinIO bucket 初始化失败: {}", bucket, e);
            throw new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED, "MinIO bucket 初始化失败");
        }
    }

    /**
     * 上传文件到 MinIO。
     * @param objectKey  对象键，格式 "{docId}/{originalName}"
     * @param inputStream 文件内容流
     * @param size        文件字节数
     * @param contentType MIME 类型
     */
    public void uploadFile(String objectKey, InputStream inputStream, long size, String contentType) {
        try {
            minioClient.putObject(
                    PutObjectArgs.builder()
                            .bucket(bucket)
                            .object(objectKey)
                            .stream(inputStream, size, -1)
                            .contentType(contentType != null ? contentType : "application/octet-stream")
                            .build());
            log.info("MinIO 上传成功: bucket={}, key={}, size={}", bucket, objectKey, size);
        } catch (Exception e) {
            log.error("MinIO 上传失败: bucket={}, key={}", bucket, objectKey, e);
            throw new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED, "文件上传失败: " + objectKey);
        }
    }

    /**
     * 从 MinIO 读取文件，返回输入流（调用方负责关闭）。
     * @param objectKey 对象键
     * @return 文件内容流
     */
    public InputStream getFile(String objectKey) {
        try {
            return minioClient.getObject(
                    GetObjectArgs.builder()
                            .bucket(bucket)
                            .object(objectKey)
                            .build());
        } catch (Exception e) {
            log.error("MinIO 文件读取失败: bucket={}, key={}", bucket, objectKey, e);
            throw new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED, "文件读取失败: " + objectKey);
        }
    }

    /**
     * 从 MinIO 删除文件。失败时仅记警告，不抛异常。
     * @param objectKey 对象键
     */
    public void deleteFile(String objectKey) {
        try {
            minioClient.removeObject(
                    RemoveObjectArgs.builder()
                            .bucket(bucket)
                            .object(objectKey)
                            .build());
            log.info("MinIO 删除成功: bucket={}, key={}", bucket, objectKey);
        } catch (Exception e) {
            log.warn("MinIO 删除失败（孤立对象可能残留）: bucket={}, key={}", bucket, objectKey, e);
        }
    }
}
