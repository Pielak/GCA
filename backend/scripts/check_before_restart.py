#!/usr/bin/env python3
"""
Pre-restart safety check — verifica se existem documentos em análise.

Uso:
  python3 check_before_restart.py [--wait TIMEOUT_SECONDS]

Exit codes:
  0 = seguro reiniciar
  1 = documentos em processamento (aguarde ou force com --force)
  2 = erro de conexão
"""

import sys
import asyncio
import argparse
from datetime import datetime, timedelta
import os

# Configurar path para imports do app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def check_processing_documents(timeout_seconds: int = 0, force: bool = False) -> int:
    """
    Verifica se existem docs em processamento.

    Args:
        timeout_seconds: tempo a aguardar se houver docs (0 = não aguarda)
        force: se True, ignora docs em processamento

    Returns:
        0 = seguro reiniciar
        1 = há docs em processamento
        2 = erro de conexão
    """
    try:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import select as _select, func
        from app.models.base import IngestedDocument

        async with AsyncSessionLocal() as db:
            # Contar docs em processamento
            result = await db.execute(
                _select(func.count(IngestedDocument.id)).where(
                    IngestedDocument.arguider_status == "processing"
                )
            )
            count_processing = result.scalar() or 0

            # Contar docs pendentes (na fila)
            result = await db.execute(
                _select(func.count(IngestedDocument.id)).where(
                    IngestedDocument.arguider_status == "pending"
                )
            )
            count_pending = result.scalar() or 0

            if count_processing == 0 and count_pending == 0:
                print("✓ Seguro reiniciar — nenhum documento em processamento")
                return 0

            if force:
                print(f"⚠ FORÇA: {count_processing} doc(s) em processamento + {count_pending} pendente(s)")
                print("  Reinicializando mesmo assim...")
                return 0

            # Há docs em processamento
            print(f"\n❌ NÃO é seguro reiniciar!")
            print(f"   📊 Status atual:")
            print(f"      • {count_processing} documento(s) em processamento (status='processing')")
            print(f"      • {count_pending} documento(s) na fila (status='pending')")
            print()

            if timeout_seconds > 0:
                print(f"⏳ Aguardando até {timeout_seconds}s para documentos finalizarem...")
                deadline = datetime.now() + timedelta(seconds=timeout_seconds)

                while datetime.now() < deadline:
                    await asyncio.sleep(2)
                    result = await db.execute(
                        _select(func.count(IngestedDocument.id)).where(
                            IngestedDocument.arguider_status == "processing"
                        )
                    )
                    count_processing = result.scalar() or 0

                    if count_processing == 0:
                        print(f"✓ Documentos finalizados! Seguro reiniciar agora.")
                        return 0

                    elapsed = (datetime.now() - (deadline - timedelta(seconds=timeout_seconds))).total_seconds()
                    remaining = timeout_seconds - elapsed
                    print(f"   Ainda {count_processing} em processamento... {remaining:.0f}s restante(s)")

                print(f"\n⏱ Timeout expirado. Ainda existem documentos em processamento.")
                print(f"   Use --force para reiniciar mesmo assim (⚠ causará retrabalho)\n")
                return 1
            else:
                print("   💡 Dica: use --wait SEGUNDOS para aguardar automaticamente")
                print("      Ex: python3 check_before_restart.py --wait 120\n")
                return 1

    except Exception as e:
        print(f"❌ Erro de conexão ao banco: {e}")
        return 2


def main():
    parser = argparse.ArgumentParser(
        description="Pre-restart safety check — verifica docs em processamento"
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        help="Tempo em segundos para aguardar documentos finalizarem (padrão: 0 = não aguarda)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Força reinicialização mesmo se houver docs em processamento (⚠ retrabalho!)"
    )

    args = parser.parse_args()

    # Rodar check
    exit_code = asyncio.run(check_processing_documents(args.wait, args.force))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
