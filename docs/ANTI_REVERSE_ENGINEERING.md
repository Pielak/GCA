# GCA — Nota técnica: proteção contra engenharia reversa

**Autor:** Luiz Carlos Pielak
**Versão:** 1.0 — 2026-04-19
**Aplica-se a:** Empacotamento de produção (Sprint 4 do MVP de distribuição)

---

## 1. Princípio honesto

**Não existe proteção absoluta contra engenharia reversa em código que roda na máquina do cliente.** Quem tem acesso físico ao binário, tempo suficiente, ferramentas profissionais (Ghidra, IDA Pro, Frida, x64dbg) e motivação, sempre pode reverter. A proteção absoluta só existe em hardware (HSM, secure enclave, atestação remota) — fora do escopo desta versão do GCA.

O que o GCA faz é **elevar o custo de reversão** ao ponto de tornar a atividade **economicamente inviável** para o cliente médio. Isso é suficiente para proteger propriedade intelectual contra concorrência casual, mas não resiste a adversário dedicado de grau estatal ou corporativo com recursos ilimitados.

Esta nota documenta as **sete camadas de proteção** implementadas e suas **limitações conhecidas**.

---

## 2. As sete camadas

### Camada 1 — Cython compile (backend Python → binário .so/.pyd)

Todo arquivo `.py` do backend (exceto `__init__.py` e código de testes) é transformado em `.c` pelo Cython e depois compilado como extensão nativa `.so` (Linux) ou `.pyd` (Windows). A imagem Docker de produção contém apenas os binários; os `.py` originais são removidos.

**Ganho**: reversão via decompilador Python (uncompyle6, decompyle3) deixa de funcionar. Só funciona decompilador de C nativo (Ghidra, IDA Pro), que produz pseudo-C ilegível — nomes mangled, estruturas de controle otimizadas, sem comentários.

**Limitação**: módulos `.so` ainda expõem símbolos das funções exportadas. Inspetor pode ver "existe função `authenticate_user`" mas o corpo está em C otimizado.

**Configuração**:

```dockerfile
FROM python:3.11-slim AS builder
RUN pip install cython==3.0.11
# ... gera .so via Cython.Build.cythonize
```

Ver `installer/Dockerfile.backend.production`.

---

### Camada 2 — PyArmor BCC wrapper (runtime check)

Sobre os `.so` do Cython, os módulos mais sensíveis (autenticação, vault, resolvedor de chaves de LLM) recebem um wrapper adicional via PyArmor BCC (BytecodeCompiler — variante gratuita).

**Ganho**: o PyArmor adiciona verificação de runtime — o módulo só carrega dentro do contexto esperado. Tentativa de executar isoladamente falha.

**Limitação**: PyArmor BCC é gratuito mas menos robusto que PyArmor 9 Pro (pago, ~US$ 129/ano). A variante paga oferece integridade cruzada entre módulos e detecção de debugger mais profunda. Upgrade opcional para clientes com requisitos mais rígidos.

---

### Camada 3 — Imagens Docker multi-stage com base mínima

Duas imagens distintas:

- **`Dockerfile.backend.production`**: stage `builder` compila, stage `runtime` copia apenas os `.so` + Python site-packages. Sem `build-essential`, sem `git`, sem `gcc`. Usuário não-root (uid 1000).
- **`Dockerfile.frontend.production`**: stage `builder` (Node Alpine) gera bundle minificado + obfuscado; stage `runtime` é `nginx:alpine` servindo estático.

**Ganho**: a imagem final não tem ferramentas de compilação. Um atacante que ganhe shell dentro do container encontra apenas binários e nenhuma toolchain para recompilar algo alterado.

**Limitação**: se o atacante tem acesso ao host Docker, ele pode montar a imagem manualmente e extrair os binários para análise offline — a proteção é contra escalonamento lateral, não contra dump do disco.

---

### Camada 4 — Registry Docker privado autenticado

As imagens do GCA ficam em registry privado (`registry.gca-produto.com`) com autenticação por token rotacionável. O cliente recebe credenciais no momento da contratação; essas credenciais são revogáveis se a chave for vazada.

**Ganho**: quem você não autoriza não baixa a imagem. Reversão exige primeiro conseguir a imagem.

**Limitação**: se o cliente legítimo tem a imagem e se torna hostil, ele já tem tudo. Essa camada protege contra vazamento público, não contra má-fé do titular da licença.

**Operação**: rotação de tokens a cada 6 meses ou mediante qualquer suspeita de vazamento. Incidentes comprovados geram renovação imediata da licença na próxima release.

---

### Camada 5 — Frontend obfuscator (javascript-obfuscator)

O bundle JavaScript passa por `javascript-obfuscator@4.1.1` com os seguintes flags:

- `control-flow-flattening` (threshold 0.75) — reescreve estruturas de controle como máquinas de estado
- `dead-code-injection` (threshold 0.4) — injeta blocos mortos para confundir análise estática
- `string-array` (base64 encoding) — strings literais viram lookup em array obfuscado
- `transform-object-keys` — propriedades de objeto renomeadas
- `compact` — whitespace removido

**Ganho**: bundle vira ilegível. Variáveis viram `_0x5e4f`, fluxo linear vira switch-case com estado, strings viram `_arr[42]`. Source maps não são emitidos em produção.

**Limitação**: aumenta o tamanho do bundle em 30–50%. Ferramentas como JStillery e hipóteses.de podem reverter parcialmente — mas exige trabalho manual intensivo por parte do atacante.

---

### Camada 6 — Integrity check no startup

O script `installer/integrity_check.py` é o primeiro comando executado pelo `CMD` do Dockerfile do backend. Ele:

1. Lê `/app/integrity.manifest.json` (gerado no build oficial, lista SHA-256 de cada `.so`).
2. (Opcional) Valida a assinatura digital do manifest com chave pública `/app/gca_pubkey.pem` — garante que o manifest não foi forjado.
3. Calcula SHA-256 de cada `.so` em runtime e compara com o manifest.
4. Se **qualquer arquivo foi modificado**, recusa subir (exit code != 0).

**Ganho**: um atacante que modifique um binário (ex: trocar verificação de licença por `return True`) quebra o SHA-256 e o container não sobe. Para modificar de verdade, precisa também forjar o manifest assinado — o que exige a chave privada do GCA.

**Limitação**: o atacante pode **remover** a verificação antes do startup (patching do próprio `integrity_check.py`). Mitigação: `integrity_check.py` também é compilado via Cython na versão final (vira `.so`), mas mesmo assim pode ser bypassado rodando a aplicação sem passar pelo `CMD` original — requer acesso root ao host.

---

### Camada 7 — Licença JWT com expiração

No startup, o backend valida `GCA_LICENSE` (variável de ambiente preenchida durante a instalação) como JWT assinado com a **chave privada do GCA**. A validação é feita com a chave pública embutida no código compilado (Cython).

**Ganho**: sem JWT válido, a aplicação não sobe (ou entra em modo read-only). O JWT contém claims: `exp` (expiração), `max_projects`, `max_users`, `tier`. Expiração atingida → aplicação bloqueia até renovar.

**Limitação**: atacante determinado pode patchar a verificação (editar o `.so` que implementa `_verify_license`). A camada 6 (integrity check) é a defesa contra esse patch — se o `.so` foi modificado, o SHA-256 muda e o startup aborta. As duas camadas se reforçam mutuamente.

---

## 3. Anti-debug runtime (adicional, em estudo)

Planejado para versão futura (não está em 1.0.0):

- **Linux**: `ptrace(PTRACE_TRACEME)` — se outro processo já está ptraceando, falha.
- **Windows**: `IsDebuggerPresent()` via `kernel32.dll`.

Implementação exige ajustes por plataforma e pode gerar falsos-positivos em ambientes de staging — por isso ficou fora do V1.

---

## 4. Resumo da postura de segurança

| Ameaça                                                     | Proteção                          | Efetividade |
|------------------------------------------------------------|-----------------------------------|-------------|
| Cliente casual copia binário para outra máquina            | Camada 4 (registry privado) + Camada 7 (JWT)     | Alta        |
| Concorrente tenta decompilar para ver algoritmos           | Camadas 1 + 2 (Cython + PyArmor)                 | Alta        |
| Adversário tenta burlar verificação de licença             | Camadas 6 + 7 (SHA-256 + JWT assinado)           | Alta        |
| Engenheiro profissional com Ghidra e dias de trabalho      | —                                                | Baixa (inevitável) |
| Vazamento público de imagem Docker                         | Camada 4 (autenticação + rotação)                | Alta        |
| Atacante copia frontend e hospeda em domínio paralelo      | Camada 5 (obfuscator) + Camada 7 (JWT)           | Média       |

**Postura final**: adequada para mercado corporativo brasileiro de médio porte. Clientes que precisam de proteção classe governo/defesa devem considerar licença Pro com PyArmor 9 + atestação remota (customização sob contrato separado).

---

## 5. O que **não** é feito (transparência)

- O GCA **não** implementa atestação remota (remote attestation).
- O GCA **não** usa secure enclave (Intel SGX, ARM TrustZone).
- O GCA **não** criptografa o `.so` em repouso (só o código-fonte deixa de ser Python legível).
- A verificação de integridade **não** cobre arquivos `.py` de `__init__.py` (esses ficam como-estão) — mas eles contêm só imports, não lógica.
- O JWT da licença **pode** ser capturado da variável de ambiente dentro do container. Um atacante com acesso root ao host consegue ler. Defesa: ninguém de fora da organização do cliente deve ter root no host de produção (isso é responsabilidade do cliente, item 3.1 do EULA).

---

## 6. Manutenção desta postura

- **Toda release nova** rebuilda imagens com novo Cython compile + novo manifest assinado.
- **Chaves de assinatura** do GCA ficam em cofre separado (recomendado: HSM físico ou serviço como AWS KMS). Rotação anual.
- **Auditorias**: recomendamos contratar consultoria externa a cada 12 meses para validar as camadas (teste de penetração focado em reversão).
- **Bugs de segurança**: canal de divulgação responsável em `security@gca-produto.com`.

---

*Fim do documento.*
