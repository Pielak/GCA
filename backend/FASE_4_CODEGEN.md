# FASE 4: Code Generation

## Overview

FASE 4 implements the Code Generation engine, leveraging evaluated project artifacts and stack recommendations to generate production-ready code using multiple LLM providers.

## Architecture

### Components

1. **LLMService** (`app/services/llm_service.py`)
   - Multi-provider LLM abstraction layer
   - Supports: Anthropic Claude, OpenAI GPT-4, Grok, DeepSeek
   - Factory pattern for client creation
   - Async credential validation

2. **CodeGenerationService** (`app/services/code_generation_service.py`)
   - Orchestrates code generation pipeline
   - Integrates with LLMService and PiloterService
   - Manages artifact creation and storage
   - Provides project and module-level generation

3. **CodeGenerationPromptBuilder** (in CodeGenerationService)
   - Dynamic prompt construction
   - Context-aware prompt generation
   - Module-specific prompt templates

4. **CodeGenerationRouter** (`app/routers/code_generation.py`)
   - REST API endpoints for code generation
   - Provider validation endpoints
   - Generation history retrieval

## Data Flow

```
Project + Artifacts
        ↓
EvaluationService (FASE 3) validates artifacts
        ↓
CodeGenerationService receives approved artifacts
        ↓
CodeGenerationPromptBuilder constructs comprehensive prompt
        ↓
LLMService (with selected provider)
        ↓
Generated Code
        ↓
Stored as Artifact in database
```

## File Structure

```
app/services/
  ├── llm_service.py                    # LLM provider abstraction
  └── code_generation_service.py        # Code generation orchestration

app/routers/
  └── code_generation.py                # REST endpoints

app/tests/
  └── test_integration_codegen_fase4.py # Integration tests (10/10 passing)

FASE_4_CODEGEN.md                       # This file
```

## LLM Providers

### Available Providers

1. **Anthropic Claude** (Recommended)
   - Model: `claude-opus-4-1`
   - API: `https://api.anthropic.com/v1`
   - Strength: Best for code generation quality
   - Env var: `ANTHROPIC_API_KEY`

2. **OpenAI GPT-4**
   - Model: `gpt-4-turbo-preview`
   - API: `https://api.openai.com/v1`
   - Strength: Advanced reasoning
   - Env var: `OPENAI_API_KEY`

3. **xAI Grok**
   - Model: `grok-1`
   - API: `https://api.x.ai/v1/completions`
   - Strength: Real-time knowledge
   - Env var: `GROK_API_KEY`

4. **DeepSeek**
   - Model: `deepseek-coder`
   - API: `https://api.deepseek.com/v1/chat/completions`
   - Strength: Specialized for coding
   - Env var: `DEEPSEEK_API_KEY`

## REST API Endpoints

### 1. Generate Project Code

```http
POST /api/v1/code-generation/project
Content-Type: application/json

{
  "project_id": "uuid",
  "gp_id": "uuid",
  "language": "python",
  "architecture": "microservices",
  "llm_provider": "anthropic",
  "api_key": "optional"
}
```

**Response:**
```json
{
  "success": true,
  "project_id": "uuid",
  "provider": "anthropic",
  "code_artifact_id": "uuid",
  "generated_code": "...code snippet...",
  "full_code_length": 15234,
  "stack_recommendations": {
    "stack": {...},
    "recommendations": [...]
  }
}
```

### 2. Generate Module Code

```http
POST /api/v1/code-generation/module
Content-Type: application/json

{
  "project_id": "uuid",
  "module_name": "auth",
  "module_type": "backend",
  "language": "python",
  "requirements": {
    "description": "JWT-based authentication",
    "requirements": "Email verification, password reset"
  },
  "llm_provider": "anthropic"
}
```

**Response:**
```json
{
  "success": true,
  "module_name": "auth",
  "module_type": "backend",
  "provider": "anthropic",
  "generated_code": "...module code..."
}
```

### 3. Validate Provider

```http
POST /api/v1/code-generation/validate-provider?provider=anthropic&api_key=optional
```

**Response:**
```json
{
  "provider": "anthropic",
  "valid": true,
  "message": "Provider credentials validated successfully"
}
```

### 4. Get Generation History

```http
GET /api/v1/code-generation/history/{project_id}?limit=10
```

**Response:**
```json
[
  {
    "artifact_id": "uuid",
    "name": "Project Name - Generated Code",
    "generated_at": "2026-04-04T10:30:00Z",
    "size_bytes": 15234
  }
]
```

### 5. List Available Providers

```http
GET /api/v1/code-generation/providers
```

**Response:**
```json
{
  "providers": [
    {
      "name": "anthropic",
      "model": "claude-opus-4-1",
      "description": "Anthropic Claude - Recommended for code generation"
    },
    ...
  ]
}
```

## Usage Examples

### Using LLMService Directly

```python
from app.services.llm_service import LLMServiceFactory, LLMProvider

# Create client
client = LLMServiceFactory.create_client(
    provider=LLMProvider.ANTHROPIC,
    api_key="sk-ant-..."
)

# Generate code
code = await client.generate(
    prompt="Generate a FastAPI application...",
    max_tokens=8000,
    temperature=0.3
)

# Validate credentials
valid = await client.validate_credentials()
```

### Using CodeGenerationService

```python
from app.services.code_generation_service import CodeGenerationService
from app.services.llm_service import LLMProvider

service = CodeGenerationService(
    db=session,
    llm_provider=LLMProvider.ANTHROPIC
)

# Generate project code
result = await service.generate_project_code(
    project_id=project_id,
    gp_id=gp_id,
    language="python",
    architecture="microservices"
)

# Generate module code
result = await service.generate_module_code(
    project_id=project_id,
    module_name="auth",
    module_type="backend",
    requirements={...}
)

# Get history
history = await service.get_generation_history(project_id, limit=10)
```

## Prompt Architecture

### Project-Level Prompt

The system generates comprehensive prompts that include:

1. **Project Context**
   - Project name, description, slug
   
2. **Artifacts Summary**
   - Requirements document
   - Architecture blueprint
   - Security specifications
   - Database schema
   - API documentation

3. **Technology Stack**
   - Language
   - Framework
   - Database
   - Frontend
   - Deployment strategy
   - Message queue
   - Cache layer

4. **Best Practices**
   - Framework-specific patterns
   - Performance recommendations
   - Security guidelines
   - Testing strategies

5. **Instructions**
   - Code quality requirements
   - Error handling expectations
   - Documentation standards
   - Type hints
   - Comments

### Module-Level Prompt

For specific modules, prompts include:

1. Module name and type
2. Detailed requirements
3. Technology stack context
4. Output format expectations

## Testing

### Test Coverage (10/10 tests passing)

1. ✅ Setup: Users and project creation
2. ✅ Prompt builder creates valid prompts
3. ✅ Module-specific prompt builder works
4. ✅ LLM factory creates all provider clients
5. ✅ CodeGenerationService initialization
6. ✅ Test artifacts creation
7. ✅ Provider validation logic
8. ✅ API key resolution from environment
9. ✅ Generation history retrieval
10. ✅ LLMProvider enum functionality

### Running Tests

```bash
PYTHONPATH=/home/luiz/GCA/backend python3 app/tests/test_integration_codegen_fase4.py
```

## Configuration

### Environment Variables

```bash
# LLM Provider API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GROK_API_KEY=...
DEEPSEEK_API_KEY=...

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/gca

# API
API_PREFIX=/api/v1
HOST=0.0.0.0
PORT=8000
DEBUG=false
```

## Integration with Previous Phases

### FASE 2: Project Management
- Provides project context and metadata
- Schema names for tenant isolation

### FASE 3: Artifact Evaluation
- Evaluated artifacts used as code generation context
- P7 security blocker prevents code generation for blocked projects
- Evaluation scores influence prompt construction

### FASE 3.5: Stack Recommendations
- N8N workflow recommendations used as technology stack
- Stack information embedded in generation prompts
- Best practices from recommendations included

## Quality Assurance

### Code Generation Best Practices

1. **Temperature Settings**
   - Project generation: 0.3 (deterministic)
   - Module generation: 0.3 (deterministic)
   - Ensures consistency and quality

2. **Token Limits**
   - Project generation: 8000 tokens
   - Module generation: 4000 tokens
   - Prevents excessive output while allowing complete code

3. **Validation**
   - Provider credentials validated before generation
   - Artifact storage with proper metadata
   - Generation history tracked for audit

## Error Handling

The service includes comprehensive error handling:

```python
# API Key not found
ValueError: API key not found for anthropic: set ANTHROPIC_API_KEY

# Provider credentials invalid
HTTPException(400): Provider validation failed

# Project not found
HTTPException(400): Project not found

# Generation failed
HTTPException(500): Code generation failed: {error details}
```

## Next Steps (FASE 5+)

1. **Code Validation**
   - Syntax validation for generated code
   - Security scanning
   - Dependency resolution

2. **Dashboard & Monitoring**
   - Generation history visualization
   - Performance metrics
   - Cost tracking by provider

3. **Enhanced Prompting**
   - Custom prompt templates
   - Context-aware prompt optimization
   - Iterative refinement based on feedback

4. **Version Control Integration**
   - Automatic commit of generated code
   - GitHub integration for PR creation
   - Code review workflows

## Performance Considerations

- **Async Operations**: All LLM calls are async for high concurrency
- **Caching**: Stack recommendations cached from N8N
- **Database Efficiency**: Artifacts stored as-is, no chunking required
- **Provider Selection**: Choose provider based on latency/quality trade-off

## Security

1. **API Key Management**
   - Keys loaded from environment variables
   - Never logged or exposed in responses
   - Optional per-request override with caution

2. **Access Control**
   - Code generation restricted to authenticated users
   - GP user ownership enforced
   - Audit logging of all generations

3. **Content Safety**
   - LLM output stored in database
   - No direct execution of generated code
   - Review required before deployment

## Troubleshooting

### Issue: API key not found
**Solution**: Set environment variable for selected provider
```bash
export ANTHROPIC_API_KEY=your_key_here
```

### Issue: Provider validation fails
**Solution**: Verify API key is valid and endpoint is accessible
```bash
curl https://api.anthropic.com/v1/ -H "Authorization: Bearer $ANTHROPIC_API_KEY"
```

### Issue: Code generation timeout
**Solution**: Reduce token limit or switch to faster provider (DeepSeek)

### Issue: Generated code quality issues
**Solution**: Review prompt context, ensure artifacts are complete and clear

## References

- LLMService: `app/services/llm_service.py` (400+ lines)
- CodeGenerationService: `app/services/code_generation_service.py` (300+ lines)
- Router: `app/routers/code_generation.py` (300+ lines)
- Tests: `app/tests/test_integration_codegen_fase4.py` (400+ lines)
