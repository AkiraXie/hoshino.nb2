import os

from hoshino import db_dir
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import Integer, Text

db_path = os.path.join(db_dir, "livedata.db")
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class LiveSub(Base):
    """直播间订阅表: room_id + group + platform 为联合主键"""
    __tablename__ = "livesub"

    room_id: Mapped[str] = mapped_column(Text, primary_key=True)
    group: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


Base.metadata.create_all(engine)


def add_subscription(group_id: int, room_id: str, name: str, platform: str = "bilibili") -> None:
    with Session() as session:
        stmt = select(LiveSub).where(
            LiveSub.group == group_id,
            LiveSub.room_id == room_id,
            LiveSub.platform == platform,
        )
        obj = session.execute(stmt).scalar_one_or_none()
        if obj:
            obj.name = name
        else:
            obj = LiveSub(group=group_id, room_id=room_id, name=name, platform=platform)
            session.add(obj)
        session.commit()


def list_group_subscriptions(group_id: int, platform: str | None = None) -> list[LiveSub]:
    with Session() as session:
        stmt = select(LiveSub).where(LiveSub.group == group_id)
        if platform:
            stmt = stmt.where(LiveSub.platform == platform)
        return session.execute(stmt).scalars().all()


def list_subscriptions_by_room(room_id: str, platform: str) -> list[LiveSub]:
    with Session() as session:
        stmt = select(LiveSub).where(
            LiveSub.room_id == room_id,
            LiveSub.platform == platform,
        )
        return session.execute(stmt).scalars().all()


def list_all_room_ids() -> list[tuple[str, str]]:
    """返回所有不重复的 (room_id, platform) 元组"""
    with Session() as session:
        rows = session.execute(
            select(LiveSub.room_id, LiveSub.platform).distinct()
        ).all()
        return [(r[0], r[1]) for r in rows]


def remove_group_subscription(group_id: int, room_id: str, platform: str = "bilibili") -> int:
    with Session() as session:
        stmt = select(LiveSub).where(
            LiveSub.group == group_id,
            LiveSub.room_id == room_id,
            LiveSub.platform == platform,
        )
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)


def remove_group_subscription_by_name(group_id: int, name: str, platform: str | None = None) -> tuple[int, str | None, str | None]:
    with Session() as session:
        stmt = select(LiveSub).where(
            LiveSub.group == group_id, LiveSub.name == name
        )
        if platform:
            stmt = stmt.where(LiveSub.platform == platform)
        rows = session.execute(stmt).scalars().all()
        target_room = rows[0].room_id if rows else None
        target_platform = rows[0].platform if rows else None
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows), target_room, target_platform
