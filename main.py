#!/usr/bin/env python3
"""
povo_manager — povoプロモコード管理アプリ
"""
import os
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

_sentry_dsn = os.getenv("SENTRY_DSN")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=0.2,
        send_default_pii=False,
    )

from database import init_db, get_db, PromoCode, UsageHistory

app = FastAPI(title="povo Manager")

# DB 初期化
init_db()

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Pydantic スキーマ ──────────────────────────────────────────────

class CodeCreate(BaseModel):
    code: str
    description: Optional[str] = ""

class UseRecord(BaseModel):
    note: Optional[str] = ""


# ── ルート ────────────────────────────────────────────────────────

@app.get("/favicon.svg")
def favicon():
    return FileResponse("static/favicon.svg", media_type="image/svg+xml")

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("static/index.html")


# ── コード管理 API ─────────────────────────────────────────────────

@app.get("/api/codes")
def list_codes(db: Session = Depends(get_db)):
    codes = db.query(PromoCode).order_by(PromoCode.created_at.desc()).all()
    return [
        {
            "id":          c.id,
            "code":        c.code,
            "description": c.description,
            "is_active":   c.is_active,
            "total_uses":  len(c.history),
            "last_used":   c.history[-1].used_at.isoformat() if c.history else None,
            "created_at":  c.created_at.isoformat(),
        }
        for c in codes
    ]


@app.post("/api/codes", status_code=201)
def add_code(body: CodeCreate, db: Session = Depends(get_db)):
    existing = db.query(PromoCode).filter(PromoCode.code == body.code).first()
    if existing:
        raise HTTPException(status_code=409, detail="このコードはすでに登録されています")
    code = PromoCode(code=body.code.strip(), description=body.description)
    db.add(code)
    db.commit()
    db.refresh(code)
    return {"id": code.id, "code": code.code}


@app.delete("/api/codes/{code_id}")
def delete_code(code_id: int, db: Session = Depends(get_db)):
    code = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="コードが見つかりません")
    db.delete(code)
    db.commit()
    return {"status": "deleted"}


@app.patch("/api/codes/{code_id}/toggle")
def toggle_active(code_id: int, db: Session = Depends(get_db)):
    code = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="コードが見つかりません")
    code.is_active = not code.is_active
    db.commit()
    return {"is_active": code.is_active}


# ── 利用記録 API ───────────────────────────────────────────────────

@app.post("/api/codes/{code_id}/use")
def record_use(code_id: int, body: UseRecord, db: Session = Depends(get_db)):
    code = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="コードが見つかりません")
    history = UsageHistory(code_id=code_id, note=body.note)
    db.add(history)
    db.commit()
    return {"total_uses": len(code.history) + 1}


@app.get("/api/codes/{code_id}/history")
def get_history(code_id: int, db: Session = Depends(get_db)):
    code = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="コードが見つかりません")
    return {
        "code": code.code,
        "description": code.description,
        "history": [
            {
                "id":      h.id,
                "used_at": h.used_at.isoformat(),
                "note":    h.note,
            }
            for h in sorted(code.history, key=lambda x: x.used_at, reverse=True)
        ]
    }


@app.patch("/api/history/{history_id}")
def update_history(history_id: int, body: UseRecord, db: Session = Depends(get_db)):
    history = db.query(UsageHistory).filter(UsageHistory.id == history_id).first()
    if not history:
        raise HTTPException(status_code=404, detail="履歴が見つかりません")
    history.note = body.note
    db.commit()
    return {"status": "updated"}


@app.delete("/api/history/{history_id}")
def delete_history(history_id: int, db: Session = Depends(get_db)):
    history = db.query(UsageHistory).filter(UsageHistory.id == history_id).first()
    if not history:
        raise HTTPException(status_code=404, detail="履歴が見つかりません")
    db.delete(history)
    db.commit()
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
