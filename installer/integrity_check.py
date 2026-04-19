#!/usr/bin/env python3
"""
Camada 6 da proteção (ver docs/ANTI_REVERSE_ENGINEERING.md):
verificação de integridade no startup.

Calcula SHA-256 dos .so binários do backend e compara com um manifest
assinado com a chave pública do GCA. Se algum arquivo foi modificado
após o build, aborta o startup com exit code != 0.

O manifest e sua assinatura são embedados na imagem Docker durante o
build oficial (via installer/build_production_images.sh).

Uso (chamado pelo CMD do Dockerfile):
    python /app/integrity_check.py && uvicorn app.main:app ...
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

MANIFEST_PATH = Path("/app/integrity.manifest.json")
SIGNATURE_PATH = Path("/app/integrity.manifest.sig")
TARGETS_DIR = Path("/app/app")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    # 1. Manifest presente?
    if not MANIFEST_PATH.exists():
        # Modo dev: manifest ausente é tolerado (sem proteção, mas
        # backend sobe). Em produção o build sempre emite manifest.
        if os.environ.get("GCA_ALLOW_NO_MANIFEST") == "1":
            print("[integrity] manifest ausente — GCA_ALLOW_NO_MANIFEST=1 (dev)")
            return 0
        print("[integrity] ERRO: manifest ausente — imagem corrompida ou dev mode")
        return 1

    # 2. Lê manifest
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[integrity] ERRO: manifest corrompido — {e}")
        return 2

    expected = manifest.get("files", {})
    if not expected:
        print("[integrity] ERRO: manifest sem lista de arquivos")
        return 3

    # 3. (Opcional) Verifica assinatura com chave pública embutida.
    # Chave pública do GCA fica em /app/gca_pubkey.pem. Usa cryptography
    # para validar SIGNATURE_PATH sobre o conteúdo de MANIFEST_PATH.
    # Se a biblioteca ou o arquivo não existirem, ignora silenciosamente
    # (camada extra opcional).
    pubkey_path = Path("/app/gca_pubkey.pem")
    if pubkey_path.exists() and SIGNATURE_PATH.exists():
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            pubkey = serialization.load_pem_public_key(pubkey_path.read_bytes())
            pubkey.verify(
                SIGNATURE_PATH.read_bytes(),
                MANIFEST_PATH.read_bytes(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            print("[integrity] assinatura do manifest: OK")
        except Exception as e:
            print(f"[integrity] ERRO: assinatura inválida — {e}")
            return 4

    # 4. Compara hashes arquivo a arquivo
    mismatches = []
    missing = []
    for rel_path, expected_hash in expected.items():
        full = Path(rel_path) if Path(rel_path).is_absolute() else TARGETS_DIR.parent / rel_path
        if not full.exists():
            missing.append(rel_path)
            continue
        actual = sha256_file(full)
        if actual != expected_hash:
            mismatches.append((rel_path, expected_hash[:12], actual[:12]))

    if missing:
        print(f"[integrity] ERRO: {len(missing)} arquivo(s) ausente(s):")
        for m in missing[:10]:
            print(f"  - {m}")
        return 5

    if mismatches:
        print(f"[integrity] ERRO: {len(mismatches)} arquivo(s) modificado(s):")
        for rel, exp, act in mismatches[:10]:
            print(f"  - {rel}: esperado {exp}..., atual {act}...")
        return 6

    print(f"[integrity] OK — {len(expected)} arquivo(s) verificados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
