"""ORM base conventions.

The naming convention is load-bearing: without it PostgreSQL names constraints
itself, and a downgrade can fail because it cannot find the constraint to drop.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import NAMING_CONVENTION, Base, TimestampedBase


class _Example(TimestampedBase):
    """A throwaway model, defined here only to inspect generated DDL."""

    __tablename__ = "example_for_tests"

    # Separate columns on purpose: `unique=True` alone yields a UniqueConstraint,
    # while pairing it with `index=True` yields a unique *index* instead. The two
    # take different names, so each convention needs its own subject.
    code: Mapped[str] = mapped_column(String(10), unique=True)
    label: Mapped[str] = mapped_column(String(10), index=True)


def test_the_metadata_carries_the_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_a_primary_key_is_named_predictably() -> None:
    """Predictable names are what make a downgrade able to find its target."""
    assert _Example.__table__.primary_key.name == "pk_example_for_tests"


def test_a_unique_constraint_is_named_predictably() -> None:
    names = {constraint.name for constraint in _Example.__table__.constraints}
    assert "uq_example_for_tests_code" in names


def test_an_index_is_named_predictably() -> None:
    names = {index.name for index in _Example.__table__.indexes}
    assert "ix_example_for_tests_label" in names


def test_identity_and_timestamps_are_present_on_every_row() -> None:
    columns = _Example.__table__.columns
    assert columns["id"].primary_key
    assert columns["created_at"].server_default is not None
    assert columns["updated_at"].server_default is not None


def test_ids_default_to_a_random_uuid_generated_per_row() -> None:
    """A shared default would collide across rows; the callable is evaluated each time."""
    default = _Example.__table__.columns["id"].default
    assert default is not None
    first, second = default.arg(None), default.arg(None)
    assert isinstance(first, uuid.UUID)
    assert first != second


def test_timestamps_are_timezone_aware() -> None:
    """Naive timestamps on evidence-adjacent data are a correctness bug."""
    assert _Example.__table__.columns["created_at"].type.timezone is True
    assert _Example.__table__.columns["updated_at"].type.timezone is True
