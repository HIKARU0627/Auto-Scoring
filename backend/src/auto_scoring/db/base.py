"""Declarative base shared by every ORM table and by Alembic's autogenerate."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root of the ORM hierarchy; ``Base.metadata`` is the migration target."""
