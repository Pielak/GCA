# GCA — Script PowerShell de instalação chamado pelo Inno Setup.
# Equivalente Windows do install.sh.
#
# Recebe os parâmetros coletados nas 9 telas do wizard e:
#   1. Valida Docker rodando
#   2. Cria pasta de instalação + .env com segredos gerados
#   3. Faz docker pull das imagens
#   4. docker compose up -d
#   5. Aguarda health check
#   6. Bootstrap do primeiro Admin

param(
    [Parameter(Mandatory=$true)] [string]$License,
    [Parameter(Mandatory=$true)] [string]$Domain,
    [Parameter(Mandatory=$true)] [string]$PortFrontend,
    [Parameter(Mandatory=$true)] [string]$PortAPI,
    [Parameter(Mandatory=$true)] [string]$AdminName,
    [Parameter(Mandatory=$true)] [string]$AdminEmail,
    [Parameter(Mandatory=$true)] [string]$AdminPassword,
    [Parameter(Mandatory=$true)] [string]$LLMProvider,
    [Parameter(Mandatory=$false)][string]$LLMApiKey = ""
)

$ErrorActionPreference = "Stop"
$InstallDir = "$env:ProgramFiles\GCA"
$LogPath = "$InstallDir\install.log"
$Registry = "registry.gca-produto.com"
$Version = "1.0.0"
$BackendImg = "${Registry}/gca-backend:${Version}"
$FrontendImg = "${Registry}/gca-frontend:${Version}"

function Write-Log { param([string]$Msg)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Msg"
    Add-Content -Path $LogPath -Value $line
    Write-Host $Msg
}

function Generate-Secret { param([int]$Length = 32)
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('/', '_').Replace('+', '-').Substring(0, $Length)
}

# Inicializa
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType File -Force -Path $LogPath | Out-Null
Write-Log "═══ GCA Install — versão $Version ═══"
Write-Log "Domínio: $Domain | Portas: $PortFrontend (front) / $PortAPI (API)"
Write-Log "Admin inicial: $AdminEmail"
Write-Log "Provedor IA: $LLMProvider"

# 1. Verifica Docker
try {
    docker version > $null 2>&1
    Write-Log "✓ Docker Desktop OK"
} catch {
    Write-Log "✗ ERRO: Docker Desktop não está rodando."
    exit 1
}

# 2. Gera .env
$EnvFile = "$InstallDir\.env"
$PostgresPwd = Generate-Secret 32
$MasterKey = Generate-Secret 44
$JwtSecret = -join ((1..96) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })

@"
# Gerado pelo install.ps1 em $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
POSTGRES_PASSWORD=$PostgresPwd
GCA_MASTER_KEY=$MasterKey
JWT_SECRET_KEY=$JwtSecret
GCA_LICENSE=$License
GCA_DOMAIN=$Domain
LLM_API_KEY=$LLMApiKey
"@ | Set-Content -Path $EnvFile -Encoding UTF8

icacls $EnvFile /inheritance:r /grant:r "Administrators:(F)" "SYSTEM:(F)" | Out-Null
Write-Log "✓ Segredos gerados em $EnvFile"

# 3. Gera docker-compose.yml
$ComposeFile = "$InstallDir\docker-compose.yml"
@"
services:
  gca-postgres:
    image: postgres:15-alpine
    container_name: gca-postgres
    environment:
      POSTGRES_USER: gca
      POSTGRES_PASSWORD: `${POSTGRES_PASSWORD}
      POSTGRES_DB: gca
    volumes:
      - gca-postgres-data:/var/lib/postgresql/data
    restart: unless-stopped
    networks: [gca-network]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gca"]
      interval: 10s
      timeout: 3s
      retries: 5

  gca-backend:
    image: $BackendImg
    container_name: gca-backend
    depends_on:
      gca-postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://gca:`${POSTGRES_PASSWORD}@gca-postgres:5432/gca
      GCA_MASTER_KEY: `${GCA_MASTER_KEY}
      JWT_SECRET_KEY: `${JWT_SECRET_KEY}
      GCA_LICENSE: `${GCA_LICENSE}
      DEFAULT_AI_PROVIDER: $LLMProvider
      STORAGE_PATH: /tmp/gca-storage
    volumes:
      - gca-uploads-storage:/tmp/gca-storage
      - gca-backups:/var/gca-backups
    ports:
      - "${PortAPI}:8000"
    restart: unless-stopped
    networks: [gca-network]

  gca-frontend:
    image: $FrontendImg
    container_name: gca-frontend
    depends_on: [gca-backend]
    ports:
      - "${PortFrontend}:80"
    restart: unless-stopped
    networks: [gca-network]

volumes:
  gca-postgres-data:
  gca-uploads-storage:
  gca-backups:

networks:
  gca-network:
    driver: bridge
"@ | Set-Content -Path $ComposeFile -Encoding UTF8

Write-Log "✓ docker-compose.yml gerado"

# 4. Pull das imagens
Write-Log "Baixando imagens..."
Push-Location $InstallDir
docker pull $BackendImg
docker pull $FrontendImg
docker pull postgres:15-alpine
Write-Log "✓ Imagens baixadas"

# 5. Sobe containers
docker compose up -d
Write-Log "✓ Containers iniciados"

# 6. Aguarda health do backend
Write-Log "Aguardando backend ficar saudável (60s)..."
$ok = $false
for ($i = 1; $i -le 60; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:$PortAPI/api/v1/metrics/health" `
            -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

if (-not $ok) {
    Write-Log "✗ Backend não respondeu em 60s. Veja: docker logs gca-backend"
    Pop-Location
    exit 2
}
Write-Log "✓ Backend saudável"

# 7. Bootstrap admin
$BootstrapBody = @{
    email = $AdminEmail
    password = $AdminPassword
    full_name = $AdminName
} | ConvertTo-Json -Compress

try {
    Invoke-RestMethod -Uri "http://localhost:$PortAPI/api/v1/auth/bootstrap" `
        -Method Post -ContentType "application/json" -Body $BootstrapBody `
        -TimeoutSec 30 | Out-Null
    Write-Log "✓ Admin inicial criado: $AdminEmail"
} catch {
    Write-Log "⚠ Bootstrap retornou erro (talvez já exista admin): $_"
}

Pop-Location
Write-Log "═══ Instalação concluída — http://${Domain}:${PortFrontend} ═══"
exit 0
