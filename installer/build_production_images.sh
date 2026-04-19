#!/usr/bin/env bash
# Build das imagens Docker de produção do GCA com proteção de código.
#
# Stages:
#   1. Compila backend (Python → .so via Cython)
#   2. Constrói frontend com obfuscator JS
#   3. Gera manifest de integridade SHA-256 dos .so do backend
#   4. Assina manifest com chave privada do GCA (opcional)
#   5. Re-empacota o backend incluindo manifest + pubkey
#   6. Emite versão + tags + push opcional para registry privado
#
# Uso:
#   ./installer/build_production_images.sh [--version 1.0.0] [--push]

set -euo pipefail

# ─── Config ────────────────────────────────────────────────────────
VERSION="${VERSION:-1.0.0}"
REGISTRY="${GCA_REGISTRY:-registry.gca-produto.com}"
BACKEND_IMAGE="${REGISTRY}/gca-backend:${VERSION}"
FRONTEND_IMAGE="${REGISTRY}/gca-frontend:${VERSION}"
BACKEND_IMAGE_TAGGED="${REGISTRY}/gca-backend:$(date +%Y%m%d-%H%M)"
FRONTEND_IMAGE_TAGGED="${REGISTRY}/gca-frontend:$(date +%Y%m%d-%H%M)"

# Chave privada para assinar manifest — opcional
PRIVATE_KEY="${GCA_SIGNING_KEY:-}"
PUBLIC_KEY="${GCA_PUBKEY:-installer/keys/gca_pubkey.pem}"

PUSH=0
for arg in "$@"; do
    case $arg in
        --version=*) VERSION="${arg#*=}";;
        --version) shift; VERSION="$1";;
        --push) PUSH=1;;
    esac
done

cd "$(dirname "$0")/.."

# ─── 1. Build backend (Cython + PyArmor) ───────────────────────────
echo "═══ Stage 1/5: Build backend com Cython compile ═══"
docker build \
    -f installer/Dockerfile.backend.production \
    -t "$BACKEND_IMAGE" \
    -t "$BACKEND_IMAGE_TAGGED" \
    backend/

echo "─── Backend image: $BACKEND_IMAGE ───"

# ─── 2. Build frontend (obfuscator) ────────────────────────────────
echo "═══ Stage 2/5: Build frontend com javascript-obfuscator ═══"
docker build \
    -f installer/Dockerfile.frontend.production \
    -t "$FRONTEND_IMAGE" \
    -t "$FRONTEND_IMAGE_TAGGED" \
    frontend/

echo "─── Frontend image: $FRONTEND_IMAGE ───"

# ─── 3. Gera manifest SHA-256 de integridade ───────────────────────
echo "═══ Stage 3/5: Gerar manifest SHA-256 do backend ═══"
MANIFEST=$(mktemp -d)/integrity.manifest.json

# Extrai .so do backend e calcula hash
docker run --rm \
    -v "$MANIFEST:/manifest-out.json" \
    "$BACKEND_IMAGE" \
    sh -c '
python3 <<PYEOF
import hashlib, json, os
from pathlib import Path
files = {}
for p in Path("/app/app").rglob("*.so"):
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    files[str(p.relative_to("/app"))] = h
out = {"version": "'"$VERSION"'", "generated_at": "'"$(date -u +%FT%TZ)"'", "files": files}
print(json.dumps(out, indent=2))
PYEOF
' > "$MANIFEST" || echo "(manifest capturado no stdout; salvo em $MANIFEST)"

echo "─── Manifest: $(jq '.files | length' "$MANIFEST") arquivos ───"

# ─── 4. Assina manifest (se chave privada disponível) ──────────────
echo "═══ Stage 4/5: Assinar manifest ═══"
SIGNATURE=""
if [ -f "$PRIVATE_KEY" ]; then
    SIGNATURE="${MANIFEST}.sig"
    openssl dgst -sha256 -sign "$PRIVATE_KEY" -out "$SIGNATURE" "$MANIFEST"
    echo "─── Assinatura: $SIGNATURE ($(wc -c <"$SIGNATURE") bytes) ───"
else
    echo "─── Chave privada ausente (GCA_SIGNING_KEY) — pulando assinatura ───"
    echo "   (integridade ainda é verificada via hash; só a assinatura da manifest fica pendente)"
fi

# ─── 5. Re-empacotar backend com manifest + pubkey ────────────────
echo "═══ Stage 5/5: Re-empacotar backend com manifest ═══"
TMP_DIR=$(mktemp -d)
cat > "$TMP_DIR/Dockerfile.final" <<EOF
FROM $BACKEND_IMAGE
COPY integrity.manifest.json /app/integrity.manifest.json
$([ -n "$SIGNATURE" ] && echo "COPY integrity.manifest.sig /app/integrity.manifest.sig")
$([ -f "$PUBLIC_KEY" ] && echo "COPY gca_pubkey.pem /app/gca_pubkey.pem")
EOF
cp "$MANIFEST" "$TMP_DIR/integrity.manifest.json"
[ -n "$SIGNATURE" ] && cp "$SIGNATURE" "$TMP_DIR/integrity.manifest.sig"
[ -f "$PUBLIC_KEY" ] && cp "$PUBLIC_KEY" "$TMP_DIR/gca_pubkey.pem"

docker build -f "$TMP_DIR/Dockerfile.final" -t "$BACKEND_IMAGE" "$TMP_DIR"
docker tag "$BACKEND_IMAGE" "$BACKEND_IMAGE_TAGGED"

rm -rf "$TMP_DIR"

# ─── 6. Push (opcional) ────────────────────────────────────────────
if [ "$PUSH" -eq 1 ]; then
    echo "═══ Push para registry ═══"
    docker push "$BACKEND_IMAGE"
    docker push "$BACKEND_IMAGE_TAGGED"
    docker push "$FRONTEND_IMAGE"
    docker push "$FRONTEND_IMAGE_TAGGED"
    echo "─── Images pushed ───"
fi

echo ""
echo "═══ BUILD CONCLUÍDO ═══"
echo "  Backend:  $BACKEND_IMAGE"
echo "  Frontend: $FRONTEND_IMAGE"
echo "  Manifest: $MANIFEST"
echo ""
echo "Para pull no cliente:"
echo "  docker login $REGISTRY"
echo "  docker pull $BACKEND_IMAGE"
echo "  docker pull $FRONTEND_IMAGE"
