-- =============================================
-- Tekvwa Pro Audit - Database Initialization
-- Run on first setup to create extensions
-- =============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_trgm for fuzzy text search
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Enable btree_gist for range types
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- Create test database if not exists (for pytest)
SELECT 'CREATE DATABASE tekvwa_pro_audit_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'tekvwa_pro_audit_test')\gexec
