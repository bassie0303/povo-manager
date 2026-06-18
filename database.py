from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

def now_utc():
    """タイムゾーン情報付きのUTC現在時刻を返す（ブラウザがJSTに自動変換）"""
    return datetime.now(timezone.utc)

import os
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./povo_manager.db")
# Railway の PostgreSQL URL は postgresql:// だが SQLAlchemy は postgresql+psycopg2:// が必要
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id          = Column(Integer, primary_key=True, index=True)
    code        = Column(String, unique=True, nullable=False)
    description = Column(String, default="")
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), default=now_utc)

    history = relationship("UsageHistory", back_populates="promo_code", cascade="all, delete-orphan")

    @property
    def total_uses(self):
        return len(self.history)


class UsageHistory(Base):
    __tablename__ = "usage_history"

    id         = Column(Integer, primary_key=True, index=True)
    code_id    = Column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    used_at    = Column(DateTime(timezone=True), default=now_utc)
    note       = Column(String, default="")

    promo_code = relationship("PromoCode", back_populates="history")


# タイムゾーン列の対象（テーブル名, 列名）
_TZ_COLUMNS = [
    ("promo_codes", "created_at"),
    ("usage_history", "used_at"),
]


def _ensure_timestamptz():
    """PostgreSQL で DateTime 列を timestamptz に揃える冪等なワンショット処理。

    マイグレーションツールが無いため、過去に `timestamp without time zone`
    （tz 無し）で作られた列が残ると、UTC の値が tz 情報なしで返り、ブラウザが
    ローカル時刻と誤読して 9 時間ずれる。起動のたびに型を確認し、未変換なら
    既存値を UTC として解釈して `timestamptz` に変換する。

    - PostgreSQL 以外（SQLite 等）は何もしない。
    - 既に timestamptz なら何もしない（毎起動で安全に再実行可能）。
    - 失敗してもアプリ起動は止めない。
    """
    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.begin() as conn:
            for table, col in _TZ_COLUMNS:
                dtype = conn.execute(
                    text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c"
                    ),
                    {"t": table, "c": col},
                ).scalar()
                if dtype == "timestamp without time zone":
                    conn.execute(
                        text(
                            f'ALTER TABLE {table} '
                            f'ALTER COLUMN {col} TYPE timestamptz '
                            f'USING {col} AT TIME ZONE \'UTC\''
                        )
                    )
    except Exception as e:
        # 起動を妨げない（次回起動で再試行される）
        print(f"[init_db] timestamptz 移行をスキップ: {e}")


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_timestamptz()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
