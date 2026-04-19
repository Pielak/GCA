#!/usr/bin/env bash
# Empacota o GCA como .deb para Ubuntu 22.04+.
#
# Estrutura final:
#   /opt/gca/
#     scripts/
#       install.sh, upgrade.sh, backup.sh, restore.sh, health-check.sh
#     systemd/
#       gca.service
#     EULA.txt
#     README.md
#
# Saída: gca_1.0.0_amd64.deb
#
# Uso:
#   cd installer/debian/
#   ./build_deb.sh

set -euo pipefail
VERSION=$(grep '^Version:' control | awk '{print $2}')
PKG_DIR="gca_${VERSION}_amd64"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "═══ Empacotando GCA v${VERSION} ═══"

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/opt/gca/scripts"
mkdir -p "$PKG_DIR/opt/gca/systemd"

# DEBIAN/
cp control "$PKG_DIR/DEBIAN/control"
cp postinst "$PKG_DIR/DEBIAN/postinst"
cp prerm "$PKG_DIR/DEBIAN/prerm"
chmod 755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/prerm"

# Scripts
cp "$ROOT/installer/install.sh" "$PKG_DIR/opt/gca/scripts/"
cp "$ROOT/scripts/upgrade.sh" "$PKG_DIR/opt/gca/scripts/" 2>/dev/null || echo "(upgrade.sh ausente)"
cp "$ROOT/scripts/backup.sh" "$PKG_DIR/opt/gca/scripts/" 2>/dev/null || echo "(backup.sh ausente)"
cp "$ROOT/scripts/restore.sh" "$PKG_DIR/opt/gca/scripts/" 2>/dev/null || echo "(restore.sh ausente)"
cp "$ROOT/scripts/health-check.sh" "$PKG_DIR/opt/gca/scripts/" 2>/dev/null || echo "(health-check.sh ausente)"
chmod +x "$PKG_DIR/opt/gca/scripts/"*.sh

# Systemd
cp gca.service "$PKG_DIR/opt/gca/systemd/"

# Docs (se existirem)
[ -f "$ROOT/installer/EULA.txt" ] && cp "$ROOT/installer/EULA.txt" "$PKG_DIR/opt/gca/"
[ -f "$ROOT/docs/ANTI_REVERSE_ENGINEERING.md" ] && cp "$ROOT/docs/ANTI_REVERSE_ENGINEERING.md" "$PKG_DIR/opt/gca/"

# Build
dpkg-deb --build "$PKG_DIR"

echo ""
echo "✓ Pacote criado: ${PKG_DIR}.deb"
echo ""
echo "Para instalar em uma máquina Ubuntu:"
echo "  sudo dpkg -i ${PKG_DIR}.deb"
echo "  sudo apt-get install -f   # resolve deps faltantes"
echo "  sudo /opt/gca/scripts/install.sh"
