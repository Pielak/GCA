"""Utilitário para geração de short_slug único para projetos."""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def generate_short_slug(name: str, db: AsyncSession) -> str:
    """Gera short_slug único (máximo 15 caracteres) a partir do nome do projeto.

    Args:
        name: Nome do projeto.
        db: Sessão assíncrona do banco de dados.

    Returns:
        String slug única com no máximo 15 caracteres.
    """
    from app.models.base import Project

    # Sanitiza: lowercase, substitui caracteres não alfanuméricos por hifens
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    slug = slug[:15].rstrip('-')

    if not slug:
        slug = 'projeto'

    # Verifica unicidade e adiciona sufixo numérico se necessário
    base_slug = slug
    counter = 2
    while True:
        result = await db.execute(
            select(Project).where(Project.short_slug == slug)
        )
        if not result.scalar_one_or_none():
            return slug
        # Trunca a base para caber o sufixo numérico
        suffix = f'-{counter}'
        max_base = 15 - len(suffix)
        slug = base_slug[:max_base].rstrip('-') + suffix
        counter += 1
