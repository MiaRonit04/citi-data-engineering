"""SQLAlchemy 2.0 ORM models for the PostgreSQL serving layer.

The Parquet Gold layer is the system of record; this normalized schema is an
*optional* relational serving copy (for BI tools / SQL access). It implements
primary keys, foreign keys, unique/NOT NULL/check constraints and indexes, and
is the source for the Mermaid ER diagram in ``docs/ER_DIAGRAM.md``.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from etl.common.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all serving-layer tables."""


class DimLocation(Base):
    __tablename__ = "dim_location"

    location_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(128), nullable=False)
    region: Mapped[str] = mapped_column(String(16), nullable=False)

    teams: Mapped[list["DimTeam"]] = relationship(back_populates="office")


class DimOrganization(Base):
    __tablename__ = "dim_organization"

    org_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    org_name: Mapped[str] = mapped_column(String(128), nullable=False)
    org_leader_email: Mapped[str] = mapped_column(String(256), nullable=False)

    teams: Mapped[list["DimTeam"]] = relationship(back_populates="organization")


class DimTeam(Base):
    __tablename__ = "dim_team"

    team_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    team_name: Mapped[str] = mapped_column(String(128), nullable=False)
    team_leader_email: Mapped[str | None] = mapped_column(String(256))
    leader_staff_type: Mapped[str | None] = mapped_column(String(16))
    reports_to_type: Mapped[str | None] = mapped_column(String(64))
    primary_office: Mapped[str | None] = mapped_column(ForeignKey("dim_location.location_code"), index=True)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("dim_organization.org_id"), index=True)

    office: Mapped["DimLocation"] = relationship(back_populates="teams")
    organization: Mapped["DimOrganization"] = relationship(back_populates="teams")
    memberships: Mapped[list["FactTeamMembership"]] = relationship(back_populates="team")
    achievements: Mapped[list["FactMonthlyAchievement"]] = relationship(back_populates="team")

    __table_args__ = (
        CheckConstraint(
            "leader_staff_type in ('direct','non_direct','unresolved') or leader_staff_type is null",
            name="ck_team_leader_staff_type",
        ),
    )


class FactTeamMembership(Base):
    __tablename__ = "fact_team_membership"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("dim_team.team_id"), nullable=False, index=True)
    employee_id: Mapped[str | None] = mapped_column(String(32), index=True)
    employee_name: Mapped[str | None] = mapped_column(String(256))
    designation: Mapped[str | None] = mapped_column(String(64))
    department: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(128))
    staff_type: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str | None] = mapped_column(String(32))

    team: Mapped["DimTeam"] = relationship(back_populates="memberships")

    __table_args__ = (
        CheckConstraint("staff_type in ('direct','non_direct','unknown') or staff_type is null",
                        name="ck_membership_staff_type"),
    )


class FactMonthlyAchievement(Base):
    __tablename__ = "fact_monthly_achievement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("dim_team.team_id"), nullable=False, index=True)
    year: Mapped[str] = mapped_column(String(4), nullable=False)
    month: Mapped[str] = mapped_column(String(2), nullable=False)
    achievement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    performance_score: Mapped[float | None] = mapped_column(Float)

    team: Mapped["DimTeam"] = relationship(back_populates="achievements")

    __table_args__ = (
        CheckConstraint("achievement_count >= 0", name="ck_achievement_count_nonneg"),
    )


class PipelineExecutionRecord(Base):
    __tablename__ = "pipeline_execution"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    start_time: Mapped[str] = mapped_column(String(32), nullable=False)
    end_time: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    rows_processed: Mapped[int] = mapped_column(Integer, nullable=False)


def get_engine(echo: bool = False):
    """Create a SQLAlchemy engine from settings."""
    return create_engine(get_settings().sqlalchemy_url, echo=echo, future=True)


def get_session_factory(echo: bool = False):
    """Return a configured sessionmaker."""
    return sessionmaker(bind=get_engine(echo), future=True)
