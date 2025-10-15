-- Initialize pgvector extension for PostgreSQL
-- This script is automatically run when the PostgreSQL container starts

CREATE EXTENSION IF NOT EXISTS vector;
