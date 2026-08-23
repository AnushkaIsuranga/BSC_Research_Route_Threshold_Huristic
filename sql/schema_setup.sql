CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE hm_clothes_100 ( 
    id SERIAL PRIMARY KEY, 
    vector_id INT, 
    index_group_name VARCHAR(255), 
    product_type_name VARCHAR(255), 
    garment_group_name VARCHAR(255), 
    perceived_colour_master_name VARCHAR(255), 
    graphical_appearance_name VARCHAR(255), 
    embedding vector(2048) 
);
CREATE TABLE hm_clothes_75 ( 
    id SERIAL PRIMARY KEY, 
    vector_id INT, 
    index_group_name VARCHAR(255), 
    product_type_name VARCHAR(255), 
    garment_group_name VARCHAR(255), 
    perceived_colour_master_name VARCHAR(255), 
    graphical_appearance_name VARCHAR(255), 
    embedding vector(2048) 
);
CREATE TABLE hm_clothes_50 ( 
    id SERIAL PRIMARY KEY, 
    vector_id INT, 
    index_group_name VARCHAR(255), 
    product_type_name VARCHAR(255), 
    garment_group_name VARCHAR(255), 
    perceived_colour_master_name VARCHAR(255), 
    graphical_appearance_name VARCHAR(255), 
    embedding vector(2048) 
);
CREATE TABLE hm_clothes_25 ( 
    id SERIAL PRIMARY KEY, 
    vector_id INT, 
    index_group_name VARCHAR(255), 
    product_type_name VARCHAR(255), 
    garment_group_name VARCHAR(255), 
    perceived_colour_master_name VARCHAR(255), 
    graphical_appearance_name VARCHAR(255), 
    embedding vector(2048) 
);
CREATE TABLE hm_clothes_0 ( 
    id SERIAL PRIMARY KEY, 
    vector_id INT, 
    index_group_name VARCHAR(255), 
    product_type_name VARCHAR(255), 
    garment_group_name VARCHAR(255), 
    perceived_colour_master_name VARCHAR(255), 
    graphical_appearance_name VARCHAR(255), 
    embedding vector(2048) 
);
