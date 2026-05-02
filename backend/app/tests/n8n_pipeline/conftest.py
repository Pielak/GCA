"""
Conftest local para testes do pipeline n8n.

Não importa app inteira — testes são puramente HTTP/integração.
"""
# Os testes só fazem HTTP requests para n8n e backend rodando.
# Não precisam de DB nem app.main.
