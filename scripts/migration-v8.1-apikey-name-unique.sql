-- v8.1: API Key 名称唯一性约束（per user）
-- 同一用户下不可重名，不同用户之间允许同名

ALTER TABLE api_keys ADD CONSTRAINT IF NOT EXISTS uq_api_keys_user_name UNIQUE(user_id, name);
