# -*- coding: utf-8 -*-
"""
Part 6 Black-Box Test Suite for Library Seat Management System.

Implements all 4 required black-box testing methods:
1. Equivalence Class Partitioning (等价类划分法): BB-EP-01 .. BB-EP-03
2. Boundary Value Analysis (边界值分析法):       BB-BVA-01 .. BB-BVA-03
3. Cause-Effect Diagram (因果图法):              BB-CE-01 .. BB-CE-05
4. Decision Table Testing (判定表法):            BB-DT-01 .. BB-DT-02
"""
from __future__ import annotations

import io
import shutil
import sys
import time
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.auth import create_access_token, get_password_hash
from backend.db import Base, get_db
from backend.main import create_app
from backend.models import Seat, User
from backend.routes import auth as auth_routes


@pytest.fixture()
def api_ctx():
    """Isolated in-memory SQLite DB + FastAPI TestClient."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    auth_routes._active_users.clear()

    db = TestingSessionLocal()
    student = User(username="stu_p6", pass_hash=get_password_hash("123456"), role="student")
    admin = User(username="adm_p6", pass_hash=get_password_hash("123456"), role="admin")
    db.add_all([student, admin])
    db.add_all(
        [
            Seat(seat_id="F1-01", floor_id="F1", has_power=False, is_empty=True),
            Seat(seat_id="F1-02", floor_id="F1", has_power=True, is_empty=True),
            Seat(seat_id="F1-03", floor_id="F1", has_power=False, is_empty=False),
            Seat(seat_id="F1-04", floor_id="F1", has_power=True, is_empty=False),
        ]
    )
    db.commit()
    db.refresh(student)
    db.refresh(admin)

    app = create_app()

    def override_get_db() -> Generator:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        if hasattr(app.state, "scheduler") and app.state.scheduler:
            app.state.scheduler.start = lambda: setattr(app.state.scheduler, "started", True)
            app.state.scheduler.shutdown = lambda: setattr(app.state.scheduler, "started", False)
        yield client, TestingSessionLocal, student.id, admin.id

    db.close()


def _login(client: TestClient, username: str, password: str = "123456") -> str:
    res = client.post("/auth/login", data={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _cleanup_report_dir(report_id: int) -> None:
    report_dir = BACKEND_ROOT / "config" / "report" / str(report_id)
    if report_dir.exists():
        shutil.rmtree(report_dir, ignore_errors=True)


# ===========================================================================
# 1. Equivalence Class Partitioning (等价类划分法)
# ===========================================================================
def test_bb_ep01_auth_token_and_logout_partitions(api_ctx):
    """BB-EP-01: Token equivalence classes for /auth/me & /auth/logout."""
    client, _, stu_id, _ = api_ctx
    token = _login(client, "stu_p6")

    # Valid Bearer token -> 200
    r_ok = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r_ok.status_code == 200
    assert r_ok.json() == {"id": stu_id, "username": "stu_p6", "role": "student"}

    # Invalid/malformed token -> 401
    r_bad = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r_bad.status_code == 401

    # Missing token -> 401
    assert client.get("/auth/me").status_code == 401

    # Token for deleted/non-existent user -> 401
    ghost_token = create_access_token(subject="deleted_user", user_id=999, role="student")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {ghost_token}"}).status_code == 401

    # Logout removes user from active set -> 200
    assert stu_id in auth_routes._active_users
    r_out = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r_out.status_code == 200
    assert r_out.json()["message"] == "Logged out successfully"
    assert stu_id not in auth_routes._active_users


@pytest.mark.parametrize(
    "filename,content_type,content,expect_ok",
    [
        ("photo.jpg", "image/jpeg", b"\xff\xd8\xff\xe0test", True),
        ("photo.jpeg", "image/jpeg", b"\xff\xd8\xff\xe0test", True),
        ("photo.png", "image/png", b"\x89PNG\r\n\x1a\n", True),
        ("anim.gif", "image/gif", b"GIF89a", False),
        ("note.txt", "text/plain", b"hello", False),
        ("noext", "image/png", b"\x89PNG\r\n\x1a\n", False),
    ],
)
def test_bb_ep02_report_upload_extension_partitions(api_ctx, filename, content_type, content, expect_ok):
    """BB-EP-02: Valid (.jpg/.jpeg/.png) vs Invalid (.gif/.txt/no-ext) partitions."""
    client, _, stu_id, _ = api_ctx
    res = client.post(
        "/reports",
        data={"seat_id": "F1-01", "reporter_id": str(stu_id), "text": "ext test"},
        files=[("images", (filename, io.BytesIO(content), content_type))],
    )
    if expect_ok:
        assert res.status_code == 200
        body = res.json()
        assert len(body["images"]) == 1
        _cleanup_report_dir(body["id"])
    else:
        assert res.status_code == 400
        assert "Unsupported file extension" in res.json()["detail"]
        assert client.get("/seats/F1-01").json()["is_reported"] is False


def test_bb_ep03_seat_lock_and_floor_query_partitions(api_ctx):
    """BB-EP-03: /seats floor filter & /admin/seats/{id}/lock equivalence classes."""
    client, _, _, _ = api_ctx
    adm_tok = _login(client, "adm_p6")
    headers = {"Authorization": f"Bearer {adm_tok}"}

    # Unfiltered /seats returns all seeded seats
    assert len(client.get("/seats").json()) == 4
    # Non-existent floor returns empty list
    assert client.get("/seats", params={"floor": "F9"}).json() == []

    # Valid lock request
    r_lock = client.post("/admin/seats/F1-02/lock", params={"minutes": 5}, headers=headers)
    assert r_lock.status_code == 200
    assert r_lock.json()["lock_until_ts"] >= int(time.time()) + 295

    # Non-existent seat lock -> 404
    r_404 = client.post("/admin/seats/F9-99/lock", params={"minutes": 5}, headers=headers)
    assert r_404.status_code == 404


# ===========================================================================
# 2. Boundary Value Analysis (边界值分析法)
# ===========================================================================
@pytest.mark.parametrize(
    "empty_cnt,total_cnt,expected_color",
    [
        (4, 4, "#60D937"),   # 100% > 50% -> Green
        (3, 4, "#60D937"),   # 75% > 50%  -> Green
        (2, 4, "#FEAE03"),   # 50% == 50% -> Yellow (exact boundary)
        (1, 4, "#FEAE03"),   # 25% <= 50% -> Yellow
        (0, 4, "#FF0000"),   # 0% == 0    -> Red
    ],
)
def test_bb_bva01_four_seat_floor_ratio_boundaries(api_ctx, empty_cnt, total_cnt, expected_color):
    """BB-BVA-01: Exact boundary values on a standard 4-seat floor (4/4, 3/4, 2/4, 1/4, 0/4)."""
    client, SessionLocal, _, _ = api_ctx
    db = SessionLocal()
    db.query(Seat).delete()
    for i in range(total_cnt):
        db.add(Seat(seat_id=f"FX-0{i+1}", floor_id="FX", is_empty=(i < empty_cnt)))
    db.commit()
    db.close()

    floors = client.get("/floors").json()
    assert len(floors) == 1
    assert floors[0]["empty_count"] == empty_cnt
    assert floors[0]["total_count"] == total_cnt
    assert floors[0]["floor_color"] == expected_color


@pytest.mark.parametrize("minutes,expected_delta_min,expected_delta_max", [(-1, -1, 2), (0, -1, 2), (1, 58, 62), (1440, 86398, 86402)])
def test_bb_bva02_seat_lock_minutes_boundaries(api_ctx, minutes, expected_delta_min, expected_delta_max):
    """BB-BVA-02: Lock duration boundaries (-1 clamped to 0, 0, 1 min, 1440 min)."""
    client, _, _, _ = api_ctx
    adm_tok = _login(client, "adm_p6")
    now = int(time.time())
    r = client.post(
        "/admin/seats/F1-01/lock",
        params={"minutes": minutes},
        headers={"Authorization": f"Bearer {adm_tok}"},
    )
    assert r.status_code == 200
    delta = r.json()["lock_until_ts"] - now
    assert expected_delta_min <= delta <= expected_delta_max


def test_bb_bva03_stats_malicious_timer_boundaries(api_ctx):
    """BB-BVA-03: Object-only occupancy duration boundaries in GET /stats/seats/{id}."""
    client, SessionLocal, _, _ = api_ctx
    now = int(time.time())
    db = SessionLocal()
    # F1-03 is occupied (is_empty=False); test 0, 7199s, 7200s
    s3 = db.query(Seat).filter_by(seat_id="F1-03").one()
    s3.occupancy_start_ts = now - 7199
    s4 = db.query(Seat).filter_by(seat_id="F1-04").one()
    s4.occupancy_start_ts = now - 7200
    s4.is_malicious = True
    db.commit()
    db.close()

    r1 = client.get("/stats/seats/F1-01").json()
    assert r1["object_only_occupy_seconds"] == 0

    r3 = client.get("/stats/seats/F1-03").json()
    assert 7199 <= r3["object_only_occupy_seconds"] <= 7205
    assert r3["is_malicious"] is False

    r4 = client.get("/stats/seats/F1-04").json()
    assert 7200 <= r4["object_only_occupy_seconds"] <= 7205
    assert r4["is_malicious"] is True


# ===========================================================================
# 3. Cause-Effect Diagram (因果图法) - POST /reports
# Causes:
#   C1: seat_id exists in DB
#   C2: images attached
#   C3: extension in {.jpg, .jpeg, .png}
#   C4: content_type starts with image/ (or extension fallback)
# Effects:
#   E1: HTTP 200 + Report(status="pending")
#   E2: seat.is_reported = True (seat_color = #FEAE03)
#   E3: image saved under config/report/{id}/
#   E4: HTTP 400 ("seat_id not found")
#   E5: HTTP 400 ("Unsupported file extension") + DB rollback
# ===========================================================================
def test_bb_ce01_cause_effect_invalid_seat_ignores_images(api_ctx):
    """BB-CE-01: C1=0 -> E4 (400 seat_id not found), regardless of text/images."""
    client, _, stu_id, _ = api_ctx
    r = client.post(
        "/reports",
        data={"seat_id": "NO-SUCH-SEAT", "reporter_id": str(stu_id), "text": "x"},
        files=[("images", ("ok.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png"))],
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "seat_id not found"


def test_bb_ce02_cause_effect_valid_seat_text_only(api_ctx):
    """BB-CE-02: C1=1, C2=0 -> E1 + E2 (no files written, images=[])."""
    client, _, stu_id, _ = api_ctx
    r = client.post(
        "/reports",
        data={"seat_id": "F1-03", "reporter_id": str(stu_id), "text": "Book only"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["images"] == []
    seat = client.get("/seats/F1-03").json()
    assert seat["is_reported"] is True
    assert seat["seat_color"] == "#FEAE03"


def test_bb_ce03_cause_effect_valid_seat_and_valid_image(api_ctx):
    """BB-CE-03: C1=1, C2=1, C3=1, C4=1 -> E1 + E2 + E3."""
    client, _, stu_id, _ = api_ctx
    r = client.post(
        "/reports",
        data={"seat_id": "F1-01", "reporter_id": str(stu_id), "text": "Evidence"},
        files=[("images", ("ev.jpg", io.BytesIO(b"\xff\xd8\xff\xe0abc"), "image/jpeg"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["images"]) == 1
    assert body["images"][0].endswith(".jpg")
    saved_file = BACKEND_ROOT / "config" / body["images"][0]
    assert saved_file.exists()
    _cleanup_report_dir(body["id"])


def test_bb_ce04_cause_effect_generic_mime_with_valid_extension_fallback(api_ctx):
    """BB-CE-04: C1=1, C2=1, C3=1, C4=generic(application/octet-stream) -> Web fallback accepts -> E1+E2+E3."""
    client, _, stu_id, _ = api_ctx
    r = client.post(
        "/reports",
        data={"seat_id": "F1-02", "reporter_id": str(stu_id), "text": "Flutter Web upload"},
        files=[("images", ("web_img.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "application/octet-stream"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["images"]) == 1
    _cleanup_report_dir(body["id"])


def test_bb_ce05_cause_effect_invalid_extension_triggers_rollback(api_ctx):
    """BB-CE-05: C1=1, C2=1, C3=0 -> E5 (400 + transaction rollback, seat remains unreported)."""
    client, SessionLocal, stu_id, _ = api_ctx
    r = client.post(
        "/reports",
        data={"seat_id": "F1-04", "reporter_id": str(stu_id), "text": "Bad ext"},
        files=[("images", ("script.py", io.BytesIO(b"print(1)"), "text/x-python"))],
    )
    assert r.status_code == 400
    assert "Unsupported file extension" in r.json()["detail"]
    # Verify neither Report row nor Seat.is_reported persisted
    db = SessionLocal()
    from backend.models import Report
    assert db.query(Report).filter_by(seat_id="F1-04").count() == 0
    assert db.query(Seat).filter_by(seat_id="F1-04").one().is_reported is False
    db.close()


# ===========================================================================
# 4. Decision Table Testing (判定表法)
# ===========================================================================
@pytest.mark.parametrize(
    "is_empty,has_power,is_reported,is_malicious,exp_seat_color,exp_admin_color",
    [
        # is_reported=False, is_malicious=False
        (True,  False, False, False, "#60D937", "#60D937"),
        (True,  True,  False, False, "#00A1FF", "#00A1FF"),
        (False, False, False, False, "#929292", "#929292"),
        (False, True,  False, False, "#929292", "#929292"),
        # is_reported=True, is_malicious=False
        (True,  False, True,  False, "#FEAE03", "#FEAE03"),
        (True,  True,  True,  False, "#FEAE03", "#FEAE03"),
        (False, False, True,  False, "#FEAE03", "#FEAE03"),
        (False, True,  True,  False, "#FEAE03", "#FEAE03"),
        # is_reported=False, is_malicious=True (admin_color inverted)
        (True,  False, False, True,  "#60D937", "#929292"),
        (True,  True,  False, True,  "#00A1FF", "#929292"),
        (False, False, False, True,  "#929292", "#60D937"),
        (False, True,  False, True,  "#929292", "#00A1FF"),
        # is_reported=True, is_malicious=True (seat_color Yellow, admin_color inverted)
        (True,  False, True,  True,  "#FEAE03", "#929292"),
        (True,  True,  True,  True,  "#FEAE03", "#929292"),
        (False, False, True,  True,  "#FEAE03", "#60D937"),
        (False, True,  True,  True,  "#FEAE03", "#00A1FF"),
    ],
)
def test_bb_dt01_seat_and_admin_color_decision_table(
    api_ctx, is_empty, has_power, is_reported, is_malicious, exp_seat_color, exp_admin_color
):
    """BB-DT-01: Exhaustive 16-rule Decision Table for seat_color & admin_color."""
    client, SessionLocal, _, _ = api_ctx
    db = SessionLocal()
    seat = db.query(Seat).filter_by(seat_id="F1-01").one()
    seat.is_empty = is_empty
    seat.has_power = has_power
    seat.is_reported = is_reported
    seat.is_malicious = is_malicious
    db.commit()
    db.close()

    res = client.get("/seats/F1-01")
    assert res.status_code == 200
    body = res.json()
    assert body["seat_color"] == exp_seat_color
    assert body["admin_color"] == exp_admin_color


def test_bb_dt02_rbac_permission_decision_table(api_ctx):
    """BB-DT-02: Decision Table for (token_state x endpoint_level) access rules."""
    client, _, _, _ = api_ctx
    stu_tok = _login(client, "stu_p6")
    adm_tok = _login(client, "adm_p6")

    matrix = [
        # (headers, endpoint, expected_status)
        ({},                                           "/seats",           200),
        ({},                                           "/auth/me",         401),
        ({},                                           "/admin/anomalies", 401),
        ({"Authorization": "Bearer bad.token.val"},    "/auth/me",         401),
        ({"Authorization": "Bearer bad.token.val"},    "/admin/anomalies", 401),
        ({"Authorization": f"Bearer {stu_tok}"},       "/seats",           200),
        ({"Authorization": f"Bearer {stu_tok}"},       "/auth/me",         200),
        ({"Authorization": f"Bearer {stu_tok}"},       "/admin/anomalies", 403),
        ({"Authorization": f"Bearer {adm_tok}"},       "/seats",           200),
        ({"Authorization": f"Bearer {adm_tok}"},       "/auth/me",         200),
        ({"Authorization": f"Bearer {adm_tok}"},       "/admin/anomalies", 200),
    ]
    for headers, url, expected_status in matrix:
        resp = client.get(url, headers=headers)
        assert resp.status_code == expected_status, f"Failed on {url} with {headers}: {resp.text}"
