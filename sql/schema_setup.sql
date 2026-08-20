CREATE EXTENSION IF NOT EXISTS vector;

-- Create tables for 100, 75, 50, 25, and 0 correlation
CREATE TABLE hm_clothes_100 ( id SERIAL PRIMARY KEY, vector_id INT, category VARCHAR(255), embedding vector(2048) );
CREATE TABLE hm_clothes_75 ( id SERIAL PRIMARY KEY, vector_id INT, category VARCHAR(255), embedding vector(2048) );
CREATE TABLE hm_clothes_50 ( id SERIAL PRIMARY KEY, vector_id INT, category VARCHAR(255), embedding vector(2048) );
CREATE TABLE hm_clothes_25 ( id SERIAL PRIMARY KEY, vector_id INT, category VARCHAR(255), embedding vector(2048) );
CREATE TABLE hm_clothes_0 ( id SERIAL PRIMARY KEY, vector_id INT, category VARCHAR(255), embedding vector(2048) );
