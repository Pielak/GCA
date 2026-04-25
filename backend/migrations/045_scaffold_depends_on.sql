-- Camada B da cascata Scaffold (2026-04-25): topologia de dependências
-- entre arquivos do plano. Cada item declara em quais peers ele depende,
-- e o execute_run faz Kahn topological sort antes do loop de geração.
-- Falha graciosa em ciclo (status='failed' com mensagem clara).
--
-- depends_on é JSON array de paths (strings). Vazio quando o item não
-- depende de ninguém (ex: README.md, package.json, configs base).

ALTER TABLE scaffold_run_items
    ADD COLUMN depends_on TEXT NOT NULL DEFAULT '[]';

COMMENT ON COLUMN scaffold_run_items.depends_on IS
    'JSON array de paths dos peers em que este arquivo depende. Vazio = sem dep. Topologia validada no execute_run (Kahn).';
