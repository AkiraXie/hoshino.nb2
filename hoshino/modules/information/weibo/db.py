import os

from hoshino import db_dir
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import Float, Integer, Text


db_path = os.path.join(db_dir, "weibodata.db")
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class WeiboDB(Base):
    __tablename__ = "weibodb"

    uid: Mapped[str] = mapped_column(Text, primary_key=True)
    group: Mapped[int] = mapped_column(Integer, primary_key=True)
    time: Mapped[float] = mapped_column(Float, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    keyword: Mapped[str] = mapped_column(Text, default="", nullable=False)


class WeiboConfig(Base):
    __tablename__ = "weiboconfig"

    group: Mapped[int] = mapped_column(Integer, primary_key=True)
    only_pic: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    send_screenshot: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    send_segments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


Base.metadata.create_all(engine)


def _normalize_flag(value: int | bool) -> int:
    return 1 if bool(value) else 0


def _get_or_create_group_config(session, group_id: int) -> WeiboConfig:
    stmt = select(WeiboConfig).where(WeiboConfig.group == group_id)
    obj = session.execute(stmt).scalar_one_or_none()
    if obj is None:
        obj = WeiboConfig(group=group_id)
        session.add(obj)
        session.commit()
    return obj


def add_or_update_subscription(
    group_id: int,
    uid: str,
    name: str,
    timestamp: float,
    keyword: str = "",
) -> None:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.group == group_id, WeiboDB.uid == uid)
        obj = session.execute(stmt).scalar_one_or_none()
        if obj:
            obj.name = name
            obj.time = timestamp
            obj.keyword = keyword
        else:
            obj = WeiboDB(
                group=group_id,
                uid=uid,
                name=name,
                time=timestamp,
                keyword=keyword,
            )
            session.add(obj)
        session.commit()


def list_group_subscriptions(group_id: int) -> list[WeiboDB]:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.group == group_id)
        return session.execute(stmt).scalars().all()


def list_group_subscriptions_by_uid(group_id: int, uid: str) -> list[WeiboDB]:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.group == group_id, WeiboDB.uid == uid)
        return session.execute(stmt).scalars().all()


def list_group_subscriptions_by_name(group_id: int, name: str) -> list[WeiboDB]:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.group == group_id, WeiboDB.name == name)
        return session.execute(stmt).scalars().all()


def list_subscriptions_by_uid(uid: str) -> list[WeiboDB]:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.uid == uid)
        return session.execute(stmt).scalars().all()


def list_subscriptions_by_name(name: str) -> list[WeiboDB]:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.name == name)
        return session.execute(stmt).scalars().all()


def remove_group_subscriptions_by_uid(group_id: int, uid: str) -> int:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.group == group_id, WeiboDB.uid == uid)
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)


def remove_group_subscriptions_by_name(
    group_id: int, name: str
) -> tuple[int, str | None]:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.group == group_id, WeiboDB.name == name)
        rows = session.execute(stmt).scalars().all()
        target_uid = rows[0].uid if rows else None
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows), target_uid


def remove_subscriptions_by_uid(uid: str) -> int:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.uid == uid)
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)


def update_subscriptions_for_uid(uid: str, timestamp: float, name: str) -> None:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.uid == uid)
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            row.time = timestamp
            row.name = name
        session.commit()


def uid_has_any_subscription(uid: str) -> bool:
    with Session() as session:
        stmt = select(WeiboDB).where(WeiboDB.uid == uid)
        return session.execute(stmt).scalar_one_or_none() is not None


def list_uid_time_pairs() -> list[tuple[str, float]]:
    with Session() as session:
        rows = session.execute(select(WeiboDB.uid, WeiboDB.time)).all()
    return [(str(uid), float(ts or 0.0)) for uid, ts in rows]


def get_group_config(group_id: int) -> WeiboConfig:
    with Session() as session:
        return _get_or_create_group_config(session, group_id)


def update_group_config(
    group_id: int,
    *,
    only_pic: int | bool | None = None,
    send_screenshot: int | bool | None = None,
    send_segments: int | bool | None = None,
) -> WeiboConfig:
    with Session() as session:
        obj = _get_or_create_group_config(session, group_id)
        if only_pic is not None:
            obj.only_pic = _normalize_flag(only_pic)
        if send_screenshot is not None:
            obj.send_screenshot = _normalize_flag(send_screenshot)
        if send_segments is not None:
            obj.send_segments = _normalize_flag(send_segments)
        session.commit()
        return obj


__all__ = [
    "Session",
    "WeiboDB",
    "WeiboConfig",
    "add_or_update_subscription",
    "get_group_config",
    "list_group_subscriptions",
    "list_group_subscriptions_by_name",
    "list_group_subscriptions_by_uid",
    "list_subscriptions_by_name",
    "list_subscriptions_by_uid",
    "list_uid_time_pairs",
    "remove_group_subscriptions_by_name",
    "remove_group_subscriptions_by_uid",
    "remove_subscriptions_by_uid",
    "uid_has_any_subscription",
    "update_group_config",
    "update_subscriptions_for_uid",
]
