#!/usr/bin/env python3
"""
Gerenciador de Backup para GCA v0.1

Cria snapshots do banco de dados antes/depois de testes:
  - Pre-test snapshot: backup antes de começar teste
  - Post-test snapshot: backup depois de terminar
  - Rollback: volta para snapshot anterior se teste deu ruim

Uso:
  python db_backup_manager.py --create-snapshot "pre-test"
  python db_backup_manager.py --list-snapshots
  python db_backup_manager.py --restore-snapshot "pre-test"
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class DBBackupManager:
    """Gerenciador de backups do banco de dados"""

    def __init__(self, db_name: str = "gca", backup_dir: Path = None):
        self.db_name = db_name
        self.backup_dir = backup_dir or Path("/home/luiz/GCA/backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.backup_dir / "backups.json"

    def _load_metadata(self) -> Dict:
        """Carrega metadata dos backups"""
        if self.metadata_file.exists():
            with open(self.metadata_file) as f:
                return json.load(f)
        return {"backups": []}

    def _save_metadata(self, metadata: Dict):
        """Salva metadata dos backups"""
        with open(self.metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

    def create_snapshot(self, snapshot_name: str) -> bool:
        """Cria um snapshot do banco de dados"""
        timestamp = datetime.now().isoformat()
        backup_file = self.backup_dir / f"{snapshot_name}_{timestamp.replace(':', '-')}.sql"

        print(f"\n📦 Criando snapshot '{snapshot_name}'...")
        print(f"   Arquivo: {backup_file}")

        try:
            # Usar pg_dump via shell
            cmd = f"pg_dump {self.db_name} > {backup_file}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"❌ Erro ao fazer dump: {result.stderr}")
                return False

            # Verificar se arquivo foi criado
            if not backup_file.exists():
                print(f"❌ Arquivo de backup não foi criado")
                return False

            file_size = backup_file.stat().st_size
            print(f"✅ Snapshot criado ({file_size / 1024 / 1024:.1f}MB)")

            # Atualizar metadata
            metadata = self._load_metadata()
            metadata["backups"].append({
                "name": snapshot_name,
                "timestamp": timestamp,
                "file": str(backup_file),
                "size_bytes": file_size,
            })
            self._save_metadata(metadata)

            return True

        except Exception as e:
            print(f"❌ Erro ao criar snapshot: {e}")
            return False

    def list_snapshots(self) -> List[Dict]:
        """Lista todos os snapshots disponíveis"""
        metadata = self._load_metadata()

        if not metadata["backups"]:
            print("\n📭 Nenhum snapshot disponível")
            return []

        print("\n📋 SNAPSHOTS DISPONÍVEIS")
        print("=" * 80)

        for i, backup in enumerate(metadata["backups"], 1):
            print(f"\n{i}. {backup['name']}")
            print(f"   Data: {backup['timestamp']}")
            print(f"   Arquivo: {backup['file']}")
            print(f"   Tamanho: {backup['size_bytes'] / 1024 / 1024:.1f}MB")

        print("\n" + "=" * 80)
        return metadata["backups"]

    def restore_snapshot(self, snapshot_name: str, force: bool = False) -> bool:
        """Restaura um snapshot do banco de dados"""
        metadata = self._load_metadata()

        # Procurar snapshot
        backup = None
        for b in metadata["backups"]:
            if b["name"] == snapshot_name:
                backup = b
                break

        if not backup:
            print(f"❌ Snapshot não encontrado: {snapshot_name}")
            return False

        backup_file = backup["file"]

        if not Path(backup_file).exists():
            print(f"❌ Arquivo de backup não existe: {backup_file}")
            return False

        if not force:
            response = input(
                f"\n⚠️  Isso vai restaurar o banco de dados para o estado de {backup['timestamp']}. "
                f"Continuar? (s/n): "
            )
            if response.lower() != "s":
                print("Cancelado.")
                return False

        print(f"\n♻️  Restaurando snapshot '{snapshot_name}'...")

        try:
            # Droppy DB atual e recrear
            drop_cmd = f"dropdb {self.db_name} --if-exists"
            subprocess.run(drop_cmd, shell=True, capture_output=True)

            create_cmd = f"createdb {self.db_name}"
            result = subprocess.run(create_cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"❌ Erro ao criar banco: {result.stderr}")
                return False

            # Restaurar do dump
            restore_cmd = f"psql {self.db_name} < {backup_file}"
            result = subprocess.run(restore_cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"❌ Erro ao restaurar: {result.stderr}")
                return False

            print(f"✅ Snapshot restaurado com sucesso")
            return True

        except Exception as e:
            print(f"❌ Erro ao restaurar snapshot: {e}")
            return False

    def cleanup_old_snapshots(self, keep_count: int = 5) -> int:
        """Remove snapshots antigos, mantendo apenas os últimos N"""
        metadata = self._load_metadata()

        if len(metadata["backups"]) <= keep_count:
            print(f"✅ Apenas {len(metadata['backups'])} snapshots ({keep_count} permitidos). Nada a limpar.")
            return 0

        # Ordenar por timestamp
        sorted_backups = sorted(metadata["backups"], key=lambda x: x["timestamp"], reverse=True)

        # Remover os antigos
        to_remove = sorted_backups[keep_count:]
        removed_count = 0

        for backup in to_remove:
            try:
                Path(backup["file"]).unlink()
                removed_count += 1
                print(f"  Removido: {backup['name']} ({backup['timestamp']})")
            except Exception as e:
                print(f"  ⚠️  Erro ao remover {backup['name']}: {e}")

        # Atualizar metadata
        metadata["backups"] = sorted_backups[:keep_count]
        self._save_metadata(metadata)

        print(f"\n✅ {removed_count} snapshots antigos removidos")
        return removed_count


def main():
    parser = argparse.ArgumentParser(
        description="Gerenciador de Backup para GCA v0.1"
    )
    parser.add_argument("--db-name", default="gca", help="Nome do banco de dados")
    parser.add_argument("--backup-dir", default="/home/luiz/GCA/backups", help="Diretório de backups")
    parser.add_argument("--create-snapshot", type=str, help="Criar snapshot com nome")
    parser.add_argument("--list-snapshots", action="store_true", help="Listar snapshots disponíveis")
    parser.add_argument("--restore-snapshot", type=str, help="Restaurar snapshot por nome")
    parser.add_argument("--cleanup", action="store_true", help="Remover snapshots antigos")
    parser.add_argument("--keep-count", type=int, default=5, help="Número de snapshots a manter")
    parser.add_argument("--force", action="store_true", help="Forçar operação sem confirmação")

    args = parser.parse_args()

    manager = DBBackupManager(db_name=args.db_name, backup_dir=Path(args.backup_dir))

    if args.create_snapshot:
        success = manager.create_snapshot(args.create_snapshot)
        return 0 if success else 1

    elif args.list_snapshots:
        manager.list_snapshots()
        return 0

    elif args.restore_snapshot:
        success = manager.restore_snapshot(args.restore_snapshot, force=args.force)
        return 0 if success else 1

    elif args.cleanup:
        manager.cleanup_old_snapshots(keep_count=args.keep_count)
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
