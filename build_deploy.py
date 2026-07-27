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
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
SRC = os.path.join(DATA, "screener.db")
DST = os.path.join(DATA, "screener_deploy.db")
# 절대날짜 고정이면 이 스크립트를 안 돌린 채 시간만 흐를수록 "슬림 DB" 취지가
# 무색해짐(2026-07 실제로 daily_prices가 무한증식해 GitHub 100MB 제한에 걸려 며칠간
# 조용히 push 실패했던 사고 원인) — app.py 차트 조회창(2년)·update_data.py 보존기간과
# 맞춰 "오늘로부터 며칠"로 상대화.
PRICE_RETENTION_DAYS = 730
# 슬림 DB의 daily_prices는 open/high/low를 빼고 close·volume만 담는다(화면 어디에서도
# 안 씀 — 원본 로컬 DB만 bt_run.py용으로 그대로 보존).
_SLIM_DAILY_PRICES = """
CREATE TABLE daily_prices (
    code TEXT NOT NULL, date TEXT NOT NULL, close REAL, volume INTEGER,
    PRIMARY KEY (code, date)
);
"""


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
    price_cutoff = (datetime.now() - timedelta(days=PRICE_RETENTION_DAYS)).strftime("%Y-%m-%d")
    if os.path.exists(DST):
        os.remove(DST)
    dst = sqlite3.connect(DST)
    dst.executescript(db.SCHEMA)          # 빈 테이블 생성(전체 스키마)
    dst.execute("DROP TABLE daily_prices")
    dst.executescript(_SLIM_DAILY_PRICES)  # daily_prices만 슬림 스키마로 교체
    dst.execute("ATTACH DATABASE ? AS s", (SRC,))
    dst.execute("INSERT INTO daily_prices (code,date,close,volume) "
                "SELECT code,date,close,volume FROM s.daily_prices WHERE date>=?",
                (price_cutoff,))
    dst.execute("INSERT INTO financials SELECT * FROM s.financials")
    dst.execute("INSERT INTO dividends SELECT * FROM s.dividends")
    # audit_opinions/quarterly_financials — 예전엔 여기서 안 옮겨서, 이 스크립트를
    # 재실행하면 daily-fundamentals.yml이 그동안 쌓아온 이 두 테이블 데이터가 통째로
    # 날아가는 위험이 있었음(빈 테이블로 새로 만들고 이 3개만 복사했으므로). 같이 복사.
    dst.execute("INSERT INTO audit_opinions SELECT * FROM s.audit_opinions")
    dst.execute("INSERT INTO quarterly_financials SELECT * FROM s.quarterly_financials")
    dst.commit()
    dst.execute("DETACH DATABASE s")
    dst.execute("VACUUM")
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    dst.close()
    mb = round(os.path.getsize(DST) / 1e6, 1)
    print(f"슬림 DB 생성: daily_prices {n:,}행 · {mb}MB → {DST}")
    if mb > 95:
        print(f"  ⚠️ {mb}MB — GitHub 100MB 근접. PRICE_RETENTION_DAYS를 줄이는 것 권장.")


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    precompute_rotation()
    build_slim_db()
    print("완료. 배포는 KR_DB_PATH=data/screener_deploy.db 로 실행.")
