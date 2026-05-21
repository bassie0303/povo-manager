from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

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
    created_at  = Column(DateTime, default=datetime.now)

    history = relationship("UsageHistory", back_populates="promo_code", cascade="all, delete-orphan")

    @property
    def total_uses(self):
        return len(self.history)


class UsageHistory(Base):
    __tablename__ = "usage_history"

    id         = Column(Integer, primary_key=True, index=True)
    code_id    = Column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    used_at    = Column(DateTime, default=datetime.now)
    note       = Column(String, default="")

    promo_code = relationship("PromoCode", back_populates="history")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
