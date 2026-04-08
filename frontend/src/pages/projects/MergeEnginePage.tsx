import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { GitMerge, Play, CheckCircle2, AlertTriangle, FileCode, ChevronDown, Shield, Loader2 } from 'lucide-react'
import { HelpTooltip } from '@/components/ui/HelpTooltip'

// ============================================================================
// Tipos
// ============================================================================

interface ConflictLine {
  line: number
  legacy: string
  generated: string
  type: 'conflict' | 'added' | 'removed'
}

interface MergeResult {
  confidence: number
  mergedCode: string
  conflicts: ConflictLine[]
  summary: string
}

// ============================================================================
// Mock data
// ============================================================================

const MOCK_MODULES = [
  { id: 'mod-auth', name: 'AuthModule' },
  { id: 'mod-payments', name: 'PaymentsModule' },
  { id: 'mod-users', name: 'UsersModule' },
  { id: 'mod-reports', name: 'ReportsModule' },
]

const MOCK_FILES: Record<string, string[]> = {
  'mod-auth': ['auth.py', 'views.py', 'permissions.py'],
  'mod-payments': ['processor.py', 'gateway.py', 'models.py'],
  'mod-users': ['user.py', 'serializers.py'],
  'mod-reports': ['report_gen.py', 'templates.py'],
}

const MOCK_LEGACY_CODE: Record<string, string> = {
  'auth.py': `# auth.py (legado)
import hashlib

class AuthService:
    def __init__(self, db):
        self.db = db

    def login(self, user, pwd):
        # Autenticação com MD5 (inseguro)
        hashed = hashlib.md5(pwd.encode()).hexdigest()
        query = "SELECT * FROM users WHERE username='" + user + "' AND password='" + hashed + "'"
        result = self.db.execute(query)
        if result:
            return {"token": self._generate_token(user)}
        return None

    def _generate_token(self, user):
        import time
        return hashlib.md5(f"{user}{time.time()}".encode()).hexdigest()

    def check_permission(self, user, resource):
        # Verificação hardcoded
        if user == "admin":
            return True
        return resource in ["public", "docs"]`,
  'views.py': `# views.py (legado)
from django.http import JsonResponse
from .auth import AuthService

def login_view(request):
    user = request.POST.get("username")
    pwd = request.POST.get("password")
    auth = AuthService(db)
    result = auth.login(user, pwd)
    if result:
        return JsonResponse(result)
    return JsonResponse({"error": "Invalid"}, status=401)`,
}

const MOCK_GENERATED_CODE: Record<string, string> = {
  'auth.py': `# AuthModule (GCA)
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt
from datetime import datetime, timedelta

class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def login(self, username: str, password: str) -> dict | None:
        # Autenticação segura com bcrypt + parameterized queries
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return {"token": self._generate_jwt(user)}
        return None

    def _generate_jwt(self, user) -> str:
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "exp": datetime.utcnow() + timedelta(hours=8),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    async def check_permission(self, user_id: int, resource: str) -> bool:
        # RBAC com tabela de permissões
        stmt = select(Permission).where(
            Permission.user_id == user_id,
            Permission.resource == resource
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None`,
  'views.py': `# AuthModule views (GCA)
from fastapi import APIRouter, Depends, HTTPException
from .auth import AuthService
from .schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, auth: AuthService = Depends()):
    result = await auth.login(request.username, request.password)
    if not result:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    return result`,
}

const MOCK_MERGED_CODE: Record<string, MergeResult> = {
  'auth.py': {
    confidence: 94,
    summary: '3 conflitos resolvidos: hash MD5→bcrypt, SQL injection→parameterized queries, token MD5→JWT. Lógica de check_permission do legado mantida e modernizada com RBAC.',
    conflicts: [
      { line: 11, legacy: '        hashed = hashlib.md5(pwd.encode()).hexdigest()', generated: '        if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):', type: 'conflict' },
      { line: 12, legacy: '        query = "SELECT * FROM users WHERE username=\'" + user + "\'..."', generated: '        stmt = select(User).where(User.username == username)', type: 'conflict' },
      { line: 18, legacy: '        return hashlib.md5(f"{user}{time.time()}".encode()).hexdigest()', generated: '        return jwt.encode(payload, SECRET_KEY, algorithm="HS256")', type: 'conflict' },
    ],
    mergedCode: `# AuthModule — Merge GCA (confidence: 94%)
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt
from datetime import datetime, timedelta

class AuthService:
    \"\"\"
    Serviço de autenticação modernizado pelo GCA.
    - Hash: MD5 → bcrypt (segurança)
    - Queries: concatenação → parameterized (anti-SQLi)
    - Token: MD5 → JWT com expiração (padrão OAuth2)
    - RBAC: hardcoded → tabela de permissões (do legado, modernizado)
    \"\"\"
    def __init__(self, session: AsyncSession):
        self.session = session

    async def login(self, username: str, password: str) -> dict | None:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return {"token": self._generate_jwt(user)}
        return None

    def _generate_jwt(self, user) -> str:
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "exp": datetime.utcnow() + timedelta(hours=8),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    async def check_permission(self, user_id: int, resource: str) -> bool:
        # Lógica do legado preservada e modernizada com RBAC
        stmt = select(Permission).where(
            Permission.user_id == user_id,
            Permission.resource == resource
        )
        result = await self.session.execute(stmt)
        perm = result.scalar_one_or_none()
        # Mantém acesso público do legado para recursos "public" e "docs"
        if not perm and resource in ["public", "docs"]:
            return True
        return perm is not None`,
  },
  'views.py': {
    confidence: 88,
    summary: '1 conflito: Django views→FastAPI router. Lógica de resposta mantida.',
    conflicts: [
      { line: 5, legacy: 'def login_view(request):', generated: 'async def login(request: LoginRequest, ...):', type: 'conflict' },
    ],
    mergedCode: `# AuthModule views — Merge GCA (confidence: 88%)
from fastapi import APIRouter, Depends, HTTPException
from .auth import AuthService
from .schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, auth: AuthService = Depends()):
    result = await auth.login(request.username, request.password)
    if not result:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    return result`,
  },
}

// ============================================================================
// Componente CodeBlock
// ============================================================================

function CodeBlock({ title, code, icon }: { title: string; code: string; icon?: React.ReactNode }) {
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-800 border border-slate-700 rounded-t-lg">
        {icon}
        <span className="text-xs font-medium text-slate-300 truncate">{title}</span>
      </div>
      <pre className="p-4 bg-[#0a0a14] border border-t-0 border-slate-700 rounded-b-lg overflow-x-auto text-xs leading-relaxed text-slate-300 font-mono max-h-[400px] overflow-y-auto">
        {code}
      </pre>
    </div>
  )
}

// ============================================================================
// Componente principal
// ============================================================================

export function MergeEnginePage() {
  const { id } = useParams<{ id: string }>()
  const [selectedModule, setSelectedModule] = useState(MOCK_MODULES[0].id)
  const [selectedFile, setSelectedFile] = useState(MOCK_FILES[MOCK_MODULES[0].id][0])
  const [comparing, setComparing] = useState(false)
  const [compared, setCompared] = useState(false)
  const [mergeApplied, setMergeApplied] = useState<string | null>(null)

  const availableFiles = MOCK_FILES[selectedModule] || []
  const legacyCode = MOCK_LEGACY_CODE[selectedFile]
  const generatedCode = MOCK_GENERATED_CODE[selectedFile]
  const mergeResult = MOCK_MERGED_CODE[selectedFile]

  const handleModuleChange = (moduleId: string) => {
    setSelectedModule(moduleId)
    const files = MOCK_FILES[moduleId] || []
    setSelectedFile(files[0] || '')
    setCompared(false)
    setMergeApplied(null)
  }

  const handleCompare = () => {
    if (!legacyCode || !generatedCode) return
    setComparing(true)
    setMergeApplied(null)
    setTimeout(() => {
      setComparing(false)
      setCompared(true)
    }, 1500)
  }

  const handleApplyMerge = (action: 'suggested' | 'generated' | 'existing') => {
    setMergeApplied(action)
  }

  const confidenceColor = (c: number) => {
    if (c >= 80) return 'text-emerald-400'
    if (c >= 60) return 'text-amber-400'
    return 'text-red-400'
  }

  const confidenceBg = (c: number) => {
    if (c >= 80) return 'bg-emerald-500'
    if (c >= 60) return 'bg-amber-500'
    return 'bg-red-500'
  }

  return (
    <div className="p-6 space-y-6 bg-[#0D0D18] min-h-screen">
      {/* ── Toolbar ── */}
      <div className="flex items-center gap-3">
        <GitMerge className="w-5 h-5 text-violet-400" />
        <h2 className="text-lg font-semibold text-slate-100">Merge Engine</h2>
        <HelpTooltip
          text="O MergeEngine compara o código gerado pelo GCA com o código existente no repositório para o mesmo módulo, e propõe automaticamente um merge inteligente. O objetivo é aproveitar o que já funciona no sistema legado enquanto incorpora as melhorias geradas pela IA. O score de confiança indica o quão seguro é aceitar o merge sugerido sem revisão humana."
          position="bottom"
        />
        <span className="ml-auto text-xs text-slate-500">Projeto #{id}</span>
      </div>

      {/* ── Seletores ── */}
      <div className="flex flex-wrap items-end gap-4 p-4 bg-slate-900 border border-slate-800 rounded-xl">
        <div className="flex-1 min-w-[180px]">
          <label className="text-slate-500 text-xs block mb-1.5">Módulo</label>
          <div className="relative">
            <select
              value={selectedModule}
              onChange={e => handleModuleChange(e.target.value)}
              className="w-full appearance-none bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500 pr-8"
            >
              {MOCK_MODULES.map(m => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
          </div>
        </div>

        <div className="flex-1 min-w-[180px]">
          <label className="text-slate-500 text-xs block mb-1.5">Arquivo existente</label>
          <div className="relative">
            <select
              value={selectedFile}
              onChange={e => { setSelectedFile(e.target.value); setCompared(false); setMergeApplied(null) }}
              className="w-full appearance-none bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500 pr-8"
            >
              {availableFiles.map(f => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
          </div>
        </div>

        <button
          onClick={handleCompare}
          disabled={comparing || !legacyCode || !generatedCode}
          className="flex items-center gap-2 px-5 py-2 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {comparing ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Comparando...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Comparar
            </>
          )}
        </button>
      </div>

      {/* ── Aviso se arquivo não tem dados ── */}
      {(!legacyCode || !generatedCode) && (
        <div className="flex items-center gap-3 p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <p className="text-slate-400 text-sm">
            Nenhum código legado ou gerado disponível para o arquivo <span className="font-mono text-slate-300">{selectedFile}</span>.
            Selecione um módulo e arquivo com dados para comparar.
          </p>
        </div>
      )}

      {/* ── Painéis de comparação ── */}
      {compared && legacyCode && generatedCode && (
        <div className="space-y-6">
          {/* Side-by-side code */}
          <div className="flex flex-col lg:flex-row gap-4">
            <CodeBlock
              title={`${selectedFile} (legado)`}
              code={legacyCode}
              icon={<FileCode className="w-3.5 h-3.5 text-amber-400" />}
            />
            <CodeBlock
              title={`${MOCK_MODULES.find(m => m.id === selectedModule)?.name || 'Módulo'} (GCA)`}
              code={generatedCode}
              icon={<FileCode className="w-3.5 h-3.5 text-emerald-400" />}
            />
          </div>

          {/* Conflitos detectados */}
          {mergeResult && mergeResult.conflicts.length > 0 && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <h3 className="text-slate-200 text-sm font-semibold">
                  {mergeResult.conflicts.length} conflito{mergeResult.conflicts.length > 1 ? 's' : ''} detectado{mergeResult.conflicts.length > 1 ? 's' : ''}
                </h3>
              </div>
              <div className="space-y-2">
                {mergeResult.conflicts.map((c, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/50">
                    <span className="text-xs text-slate-500 font-mono mt-0.5 flex-shrink-0">L{c.line}</span>
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-red-400 text-xs font-medium">LEGADO</span>
                        <code className="text-xs text-red-300/80 font-mono truncate block">{c.legacy}</code>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-400 text-xs font-medium">GCA&nbsp;&nbsp;&nbsp;</span>
                        <code className="text-xs text-emerald-300/80 font-mono truncate block">{c.generated}</code>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Merge sugerido */}
          {mergeResult && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-800">
                <Shield className="w-4 h-4 text-violet-400" />
                <h3 className="text-slate-200 text-sm font-semibold">
                  Merge Sugerido
                </h3>
                <HelpTooltip
                  text="Código resultante da mesclagem automática pelo GCA. O algoritmo prioriza: (1) corrigir vulnerabilidades de segurança do código legado, (2) modernizar patterns obsoletos, (3) manter lógica de negócio específica do legado que não estava no OCG. Score de confiança > 80% = merge seguro para aplicar diretamente. < 80% = revisar manualmente antes de aplicar."
                  position="right"
                />
                <div className="ml-auto flex items-center gap-3">
                  {/* Confidence badge */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">Confiança:</span>
                    <div className="flex items-center gap-1.5">
                      <div className="w-20 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${confidenceBg(mergeResult.confidence)}`}
                          style={{ width: `${mergeResult.confidence}%` }}
                        />
                      </div>
                      <span className={`text-sm font-bold ${confidenceColor(mergeResult.confidence)}`}>
                        {mergeResult.confidence}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Summary */}
              <div className="px-5 py-3 border-b border-slate-800/50 bg-slate-800/20">
                <p className="text-xs text-slate-400 leading-relaxed">{mergeResult.summary}</p>
              </div>

              {/* Merged code */}
              <pre className="p-5 overflow-x-auto text-xs leading-relaxed text-slate-300 font-mono max-h-[450px] overflow-y-auto bg-[#0a0a14]">
                {mergeResult.mergedCode}
              </pre>
            </div>
          )}

          {/* Ações */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => handleApplyMerge('suggested')}
              disabled={mergeApplied !== null}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <CheckCircle2 className="w-4 h-4" />
              Aplicar Merge Sugerido
              <HelpTooltip
                text="Commita o código mesclado no repositório do projeto, substituindo o arquivo existente. Esta ação é irreversível via interface — use git revert no repositório se necessário. Disponível apenas para usuários com papel Developer ou GP. A ação é registrada no audit log com o usuário, timestamp e diff aplicado."
                position="top"
              />
            </button>

            <button
              onClick={() => handleApplyMerge('generated')}
              disabled={mergeApplied !== null}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <FileCode className="w-4 h-4" />
              Usar Gerado
            </button>

            <button
              onClick={() => handleApplyMerge('existing')}
              disabled={mergeApplied !== null}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-700 text-slate-200 text-sm font-medium hover:bg-slate-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Shield className="w-4 h-4" />
              Manter Existente
            </button>

            {mergeApplied && (
              <div className="flex items-center gap-2 ml-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span className="text-sm text-emerald-400 font-medium">
                  {mergeApplied === 'suggested' && 'Merge sugerido aplicado com sucesso'}
                  {mergeApplied === 'generated' && 'Código gerado aplicado com sucesso'}
                  {mergeApplied === 'existing' && 'Código existente mantido'}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
