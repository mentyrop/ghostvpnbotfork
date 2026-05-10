"""Resilience when provider payment tables are missing (skipped migrations, forked revision graphs).

Admin search and pending-payment listing query every provider; a single absent table must not 500 the app.
New providers stay safe as long as they go through the helpers below.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable
from typing import Any, TypeVar

import structlog
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

_T = TypeVar('_T')

_MISSING_RELATION_RE = re.compile(r'relation\s+"([^"]+)"\s+does not exist', re.IGNORECASE)


def missing_pg_relation_name(exc: BaseException) -> str | None:
    """Return PostgreSQL relation name if *exc* is 'relation "x" does not exist', else None."""
    m = _MISSING_RELATION_RE.search(str(exc))
    return m.group(1) if m else None


def is_postgres_undefined_table(exc: BaseException, *, relation: str) -> bool:
    """True if *exc* is a missing-relation error for the given table name (asyncpg/SQLAlchemy)."""
    if not isinstance(exc, ProgrammingError):
        return False
    msg = str(exc).lower()
    rel = relation.lower()
    return rel in msg and ('does not exist' in msg or 'undefinedtable' in msg)


async def list_or_empty_if_table_missing(awaitable: Awaitable[list[_T]]) -> list[_T]:
    """Await a coroutine that returns a list; on missing PG relation return []."""
    try:
        return await awaitable
    except ProgrammingError as e:
        rel = missing_pg_relation_name(e)
        if rel is not None:
            logger.warning(
                'skipping provider batch: table or relation missing',
                relation=rel,
                error=str(e),
            )
            return []
        raise


async def value_or_none_if_table_missing(awaitable: Awaitable[_T]) -> _T | None:
    """Await a coroutine; on missing PG relation return None (for single-record loads)."""
    try:
        return await awaitable
    except ProgrammingError as e:
        rel = missing_pg_relation_name(e)
        if rel is not None:
            logger.warning(
                'payment record query skipped: table or relation missing',
                relation=rel,
                error=str(e),
            )
            return None
        raise


async def scalars_all_from_stmt(
    db: AsyncSession,
    stmt: Any,
    *,
    orm_model: type[Any],
) -> list[Any]:
    """Run ``select``/ORM statement; return rows or [] if *orm_model*'s table is missing."""
    relation = getattr(orm_model, '__tablename__', None)
    if relation is None:
        raise TypeError('orm_model must define __tablename__')
    try:
        result = await db.execute(stmt)
        return list(result.scalars().all())
    except ProgrammingError as e:
        if is_postgres_undefined_table(e, relation=relation):
            logger.warning(
                'skipping provider query: expected table missing',
                table=relation,
                error=str(e),
            )
            return []
        raise


async def get_instance_or_none_if_table_missing(
    db: AsyncSession,
    orm_model: type[Any],
    pk: Any,
) -> Any | None:
    """``session.get`` that returns None when the mapped table does not exist."""
    relation = getattr(orm_model, '__tablename__', None)
    if relation is None:
        raise TypeError('orm_model must define __tablename__')
    try:
        return await db.get(orm_model, pk)
    except ProgrammingError as e:
        if is_postgres_undefined_table(e, relation=relation):
            logger.warning('session.get skipped: table missing', table=relation, error=str(e))
            return None
        raise
