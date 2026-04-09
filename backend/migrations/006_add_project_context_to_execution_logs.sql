-- Migration 006: Adicionar contexto do projeto e aderência aos logs de execução
-- Regra: logs devem conter código/nome/slug do projeto, tipo de teste, percentual de aderência

ALTER TABLE test_execution_logs ADD COLUMN IF NOT EXISTS project_code VARCHAR(50);
ALTER TABLE test_execution_logs ADD COLUMN IF NOT EXISTS project_name VARCHAR(255);
ALTER TABLE test_execution_logs ADD COLUMN IF NOT EXISTS project_slug VARCHAR(100);
ALTER TABLE test_execution_logs ADD COLUMN IF NOT EXISTS test_type VARCHAR(20);
ALTER TABLE test_execution_logs ADD COLUMN IF NOT EXISTS adherence_percent FLOAT;
