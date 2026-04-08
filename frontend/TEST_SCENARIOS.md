# Session 08 — Error Scenario Testing

## Manual Test Cases

### 1. **401 Unauthorized** (Token Expirado)
**Como reproduzir**:
```bash
# No console do navegador, remova o token
localStorage.removeItem('token')
localStorage.removeItem('auth-storage')

# Tente acessar http://localhost:5173/admin/dashboard
```

**Esperado**:
- ✓ Redirecionado para login
- ✓ Mensagem clara de erro
- ✓ Sem crash na UI

**Verificação**:
- [ ] Login page carrega
- [ ] Mensagem de erro visível
- [ ] Nenhum erro no console

---

### 2. **404 Not Found** (Usuário Inexistente)
**Como reproduzir**:
```bash
# Substitua no código uma URL válida por inválida
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/admin/users/invalid-id/lock
```

**Esperado**:
- ✓ API retorna 404
- ✓ Toast de erro exibido
- ✓ Sem crash UI

**Verificação**:
- [ ] Toast notification aparece com mensagem de erro
- [ ] Página permanece funcional
- [ ] Usuário pode tentar novamente

---

### 3. **500 Server Error** (Backend Down)
**Como reproduzir**:
```bash
# Pare o backend
docker-compose stop gca-backend

# Tente carregar /admin/dashboard
```

**Esperado**:
- ✓ Mensagem de erro do servidor
- ✓ Retry button disponível
- ✓ UI não quebra

**Verificação**:
- [ ] Erro exibido amigavelmente
- [ ] Nenhum console error crítico
- [ ] Backend pode ser reiniciado e funcionará novamente

---

### 4. **Conexão Perdida** (Network Offline)
**Como reproduzir**:
```bash
# No Chrome DevTools: Ctrl+Shift+J → Network tab
# Marque "Offline" antes de fazer uma requisição
```

**Esperado**:
- ✓ Erro de conexão tratado
- ✓ Mensagem clara ao usuário
- ✓ Sem crash UI

**Verificação**:
- [ ] Toast com "Erro de conexão"
- [ ] UI responsiva mesmo offline
- [ ] Volta a funcionar quando online

---

### 5. **Timeout** (Requisição Lenta)
**Como reproduzir**:
```bash
# No backend, aumente artificialmente a latência
# Ou use Chrome DevTools: Network → Throttling → Slow 3G
```

**Esperado**:
- ✓ Spinner de loading visível
- ✓ Timeout tratado com mensagem
- ✓ Retry possível

**Verificação**:
- [ ] Spinner aparece durante requisição
- [ ] Se timeout, mensagem de erro é exibida
- [ ] Botão de retry funciona

---

### 6. **Erro de Validação** (Formulário Inválido)
**Como reproduzir**:
1. Ir para Admin → Parametrização → SMTP
2. Deixar campos vazios
3. Clicar "Salvar Configuração"

**Esperado**:
- ✓ Validação de formulário funciona
- ✓ Erros de campo exibidos (Zod)
- ✓ API não é chamada com dados inválidos

**Verificação**:
- [ ] Mensagens de erro aparecem próximas aos campos
- [ ] Botão submit desabilitado ou com aviso
- [ ] Sem requisição ao backend

---

### 7. **Error Boundary** (Crash de Componente)
**Como reproduzir**:
```javascript
// No console, force um erro em um componente
throw new Error("Teste Error Boundary")
```

**Esperado**:
- ✓ Error Boundary captura erro
- ✓ UI mostra mensagem amigável
- ✓ Botão "Recarregar Página" funciona

**Verificação**:
- [ ] Erro é renderizado em uma tela de erro
- [ ] Não crash total da aplicação
- [ ] Reload restaura UI

---

## ✅ Checklist de Conclusão

- [ ] Teste 1: 401 Unauthorized
- [ ] Teste 2: 404 Not Found
- [ ] Teste 3: 500 Server Error
- [ ] Teste 4: Conexão Perdida
- [ ] Teste 5: Timeout
- [ ] Teste 6: Validação de Formulário
- [ ] Teste 7: Error Boundary

**Resultado**: ✅ Todos passaram → Session 08 CONCLUÍDA
