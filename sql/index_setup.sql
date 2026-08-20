SET maintenance_work_mem = '2GB';

-- 100% Correlation (already started, but we can do it again with IF NOT EXISTS or just let it fail if it exists)
CREATE INDEX ON hm_clothes_100 (category);
CREATE INDEX IF NOT EXISTS hm_clothes_100_embedding_idx ON hm_clothes_100 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- 75% Correlation
CREATE INDEX ON hm_clothes_75 (category);
CREATE INDEX ON hm_clothes_75 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- 50% Correlation
CREATE INDEX ON hm_clothes_50 (category);
CREATE INDEX ON hm_clothes_50 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- 25% Correlation
CREATE INDEX ON hm_clothes_25 (category);
CREATE INDEX ON hm_clothes_25 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- 0% Correlation
CREATE INDEX ON hm_clothes_0 (category);
CREATE INDEX ON hm_clothes_0 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);
