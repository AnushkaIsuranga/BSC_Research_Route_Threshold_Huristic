SET maintenance_work_mem = '2GB';

-- 100% Correlation
CREATE INDEX ON hm_clothes_100 (index_group_name);
CREATE INDEX ON hm_clothes_100 (product_type_name);
CREATE INDEX ON hm_clothes_100 (garment_group_name);
CREATE INDEX ON hm_clothes_100 (perceived_colour_master_name);
CREATE INDEX ON hm_clothes_100 (graphical_appearance_name);
CREATE INDEX IF NOT EXISTS hm_clothes_100_embedding_idx ON hm_clothes_100 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- 75% Correlation
CREATE INDEX ON hm_clothes_75 (index_group_name);
CREATE INDEX ON hm_clothes_75 (product_type_name);
CREATE INDEX ON hm_clothes_75 (garment_group_name);
CREATE INDEX ON hm_clothes_75 (perceived_colour_master_name);
CREATE INDEX ON hm_clothes_75 (graphical_appearance_name);
CREATE INDEX ON hm_clothes_75 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- 50% Correlation
CREATE INDEX ON hm_clothes_50 (index_group_name);
CREATE INDEX ON hm_clothes_50 (product_type_name);
CREATE INDEX ON hm_clothes_50 (garment_group_name);
CREATE INDEX ON hm_clothes_50 (perceived_colour_master_name);
CREATE INDEX ON hm_clothes_50 (graphical_appearance_name);
CREATE INDEX ON hm_clothes_50 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- 25% Correlation
CREATE INDEX ON hm_clothes_25 (index_group_name);
CREATE INDEX ON hm_clothes_25 (product_type_name);
CREATE INDEX ON hm_clothes_25 (garment_group_name);
CREATE INDEX ON hm_clothes_25 (perceived_colour_master_name);
CREATE INDEX ON hm_clothes_25 (graphical_appearance_name);
CREATE INDEX ON hm_clothes_25 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- 0% Correlation
CREATE INDEX ON hm_clothes_0 (index_group_name);
CREATE INDEX ON hm_clothes_0 (product_type_name);
CREATE INDEX ON hm_clothes_0 (garment_group_name);
CREATE INDEX ON hm_clothes_0 (perceived_colour_master_name);
CREATE INDEX ON hm_clothes_0 (graphical_appearance_name);
CREATE INDEX ON hm_clothes_0 USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);
