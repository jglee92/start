# -*- coding: utf-8 -*-
"""
배포용 산출물 생성:
 1) data/sector_rotation.json  — 섹터 로테이션 미리 계산(깊은 히스토리 필요분 제거)
 2) data/screener_deploy.db    — 최근 가격만 남긴 슬림 DB (GitHub 업로드 가능 크기)

배포 서버는 KR_DB_PATH=data/screener_deploy.db 로 이 DB를 쓰고,
섹터 로테이션은 미리 계산된 JSON을 읽는다(전체 히스토리 불필요).
"""
from __future__ import annotations
import os
import sys
import json
import sqlite3

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
SRC = os.path.join(DATA, "screener.db")
DST = os.path.join(DATA, "screener_deploy.db")
PRICE_CUTOFF = "2024-04-01"   # 이 날짜 이후 가격만 배포 DB에 포함(차트·테마성과·랭킹용)
# ↑ YoY(전년동기대비) 계산엔 최소 1년+여유가 필요해 2025-01-01→2024-04-01로 확장.


def precompute_rotation():
    import db
    from factor.sector_rotation import compute_rotation
    conn = db.connect()
    rot = compute_rotation(conn)
    conn.close()
    with open(os.path.join(DATA, "sector_rotation.json"), "w", encoding="utf-8") as f:
        json.dump(rot, f, ensure_ascii=False)
    print(f"섹터 로테이션 미리계산 완료: {len(rot['rows'])}섹터 · {len(rot['years'])}년")


def build_slim_db():
    import db
    if os.path.exists(DST):
        os.remove(DST)
    dst = sqlite3.connect(DST)
    dst.executescript(db.SCHEMA)          # 빈 테이블 생성
    dst.execute("ATTACH DATABASE ? AS s", (SRC,))
    dst.execute("INSERT INTO daily_prices SELECT * FROM s.daily_prices WHERE date>=?",
                (PRICE_CUTOFF,))
    dst.execute("INSERT INTO financials SELECT * FROM s.financials")
    dst.execute("INSERT INTO dividends SELECT * FROM s.dividends")
    dst.commit()
    dst.execute("DETACH DATABASE s")
    dst.execute("VACUUM")
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    dst.close()
    mb = round(os.path.getsize(DST) / 1e6, 1)
    print(f"슬림 DB 생성: daily_prices {n:,}행 · {mb}MB → {DST}")
    if mb > 95:
        print(f"  ⚠️ {mb}MB — GitHub 100MB 근접. PRICE_CUTOFF를 더 최근으로 조정 권장.")


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    precompute_rotation()
    build_slim_db()
    print("완료. 배포는 KR_DB_PATH=data/screener_deploy.db 로 실행.")
