# GCA
Sistema de criação de Sistemas

---

# Pipeline n8n - Recomendador de Tech Stack com Qwen

## Visão Geral
Este pipeline n8n recebe informações sobre as necessidades de um projeto e utiliza a API do Qwen (Alibaba Cloud) para recomendar o melhor stack tecnológico.

## Estrutura do Pipeline

### Nodes Incluídos:

1. **Webhook** (Entrada)
   - Método: POST
   - Path: `tech-stack-recommender`
   - Recebe as necessidades do projeto em JSON

2. **Qwen API** (Processamento)
   - Endpoint: DashScope API da Alibaba Cloud
   - Modelo: `qwen-plus`
   - Envia prompt especializado para análise de arquitetura de software

3. **Parse Response** (Transformação)
   - Processa a resposta da API
   - Extrai e parseia o JSON retornado
   - Remove marcações Markdown se necessário

4. **Respond to Webhook** (Saída)
   - Retorna a recomendação formatada em JSON

## Como Usar

### 1. Importar o Workflow
- Acesse seu n8n
- Vá em "Workflows" → "Import from File"
- Selecione o arquivo `qwen-tech-stack-pipeline.json`

### 2. Configurar Credenciais
Você precisará criar uma credencial HTTP Header Auth com:
- **Name**: Qwen API Key
- **Header Name**: Authorization
- **Header Value**: `Bearer SUA_CHAVE_API_DASHSCOPE`

Para obter sua chave API:
1. Acesse [Alibaba Cloud DashScope](https://dashscope.console.aliyun.com/)
2. Crie uma conta ou faça login
3. Gere uma API Key na seção de gerenciamento de chaves

### 3. Ativar o Workflow
- Mude o status para "Active" no n8n

### 4. Fazer Requisições

**Endpoint:**
```
POST http://SEU_N8N_URL/webhook/tech-stack-recommender
```

**Payload de Exemplo:**
```json
{
  "project_requirements": "Preciso construir uma aplicação web de e-commerce com as seguintes necessidades:
  - Catálogo de produtos com busca avançada
  - Carrinho de compras e checkout
  - Integração com gateways de pagamento (Stripe, PayPal)
  - Painel administrativo para gestão de pedidos
  - Sistema de avaliações de clientes
  - Escalabilidade para Black Friday
  - Orçamento médio
  - Prazo de 3 meses"
}
```

**Resposta Esperada:**
```json
{
  "success": true,
  "project_requirements": "...",
  "recommended_stack": {
    "frontend": "React.js com Next.js",
    "backend": "Node.js com NestJS",
    "database": "PostgreSQL + Redis",
    "cloud_provider": "AWS",
    "devops_tools": ["Docker", "Kubernetes", "GitHub Actions"],
    "justification": "..."
  },
  "model_used": "qwen-plus",
  "timestamp": "2024-01-01T00:00:00.000Z"
}
```

## Personalização

### Alterar Modelo Qwen
No node "Qwen API", altere o campo `model` para:
- `qwen-turbo` - Mais rápido e econômico
- `qwen-plus` - Equilíbrio entre performance e custo (padrão)
- `qwen-max` - Máxima capacidade de raciocínio

### Ajustar Prompt do Sistema
Edite o conteúdo do node "Qwen API" para personalizar:
- Campos de saída desejados
- Estilo de recomendação
- Restrições específicas (orçamento, tecnologias preferidas, etc.)

## Requisitos

- n8n instalado e configurado
- Conta na Alibaba Cloud com acesso ao DashScope
- API Key válida do Qwen

## Troubleshooting

### Erro de Autenticação
- Verifique se a API Key está correta
- Confirme que o formato é `Bearer <sua_chave>`

### Timeout na Resposta
- Aumente o timeout no node "Qwen API" (padrão: 30s)
- Use modelos mais rápidos como `qwen-turbo`

### JSON não Parseado
- O node "Parse Response" já trata erros de formatação
- Verifique se o prompt do sistema está claro sobre o formato JSON esperado

## Segurança

- Nunca exponha sua API Key publicamente
- Use variáveis de ambiente no n8n para credenciais
- Considere adicionar autenticação no webhook em produção

---

**Autor**: Gerado automaticamente  
**Versão**: 1.0  
**Última atualização**: 2024
