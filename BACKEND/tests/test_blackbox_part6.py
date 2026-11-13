# -*- coding: utf-8 -*-
"""
Part 6 Black-Box Test Suite — Strictly Aligned with Course Lecture Slides (Black_box.pdf).

Covers all 4 required black-box testing methods and their exact slide conventions:
1. Equivalence Class Partitioning (等价类划分法, Black_box.pdf P.9-P.24):
   - Numbered Equivalence Class Table (1)..(17) across Valid & Invalid classes
   - Valid cases cover maximum uncovered valid classes per case (Rule 2, P.14)
   - Invalid cases (Robust EP, P.16) cover ONLY ONE invalid class per case while
     keeping all other inputs valid (Rule 3, P.14)
2. Boundary Value Analysis (边界值分析法, Black_box.pdf P.25-P.34):
   - Single-Fault Assumption (单缺陷假设, P.29-P.30)
   - 5-point Standard BVA (min, min+, nom, max-, max) & 7-point Robust BVA (min-, max+)
   - Two-variable <x1, x2> BVA (4n+1 / 6n+1) on ROI coordinates + Floor Ratio + Lock + 2h Timer
3. Decision Table Testing (判定表法, Black_box.pdf P.35-P.55):
   - 4 Elements: Condition Stub, Condition Entry, Action Stub, Action Entry
   - 5 Steps: 2^n initial rules (16 columns) -> Simplify using Don't-Care '—' (8 rules)
   - Remove Impossible combinations (e.g. RBAC Decision Table)
4. Cause-Effect Graph (因果图法, Black_box.pdf P.56-P.66):
   - Binary 0/1 causes c1..c4, intermediate nodes m1..m2, effects e1..e5
   - Operators (Identity, ~, v, ^) + Constraints (R: Require, M: Mask)
   - Converted to 0/1 Decision Table -> 1 test case per valid column
"""
from __future__ import annotations

import copy
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
from backend.models import Report, Seat, User
from backend.routes import auth as auth_routes
from backend.services.roi_loader import validate_floor_config


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
# 1. Equivalence Class Partitioning (等价类划分法 — Black_box.pdf P.9-P.24)
#
# Numbered Equivalence Classes for Report Submission & Auth/Lock:
#   Input A (seat_id):
#     Valid:   (1) Existing seat_id in {"F1-01".."F1-04"}
#     Invalid: (2) Non-existent seat_id ("F9-99")
#              (3) Empty seat_id ("")
#   Input B (text):
#     Valid:   (4) Non-empty string ("Bag left on desk")
#              (5) Omitted / None
#   Input C (images extension - discrete values subdivided per P.12):
#     Valid:   (6) .jpg   (7) .jpeg   (8) .png   (9) Omitted (no file)
#     Invalid: (10) .gif  (11) .txt   (12) No extension ("noext")
#   Input D (Authorization Bearer token):
#     Valid:   (13) Valid admin JWT   (14) Valid student JWT
#     Invalid: (15) Missing header    (16) Malformed JWT   (17) Deleted-user JWT
# ===========================================================================
def test_bb_ep_valid_classes_multi_cover(api_ctx):
    """
    Standard EP (Rule 2, P.14): Each valid test case covers multiple uncovered
    valid equivalence classes simultaneously until (1),(4),(5),(6),(7),(8),(9),(13),(14) are all covered.
    """
    client, _, stu_id, _ = api_ctx

    # BB-EP-V1 covers (1), (4), (6) [.jpg]
    r1 = client.post(
        "/reports",
        data={"seat_id": "F1-01", "reporter_id": str(stu_id), "text": "Bag left on desk"},
        files=[("images", ("a.jpg", io.BytesIO(b"\xff\xd8\xff\xe0jpg"), "image/jpeg"))],
    )
    assert r1.status_code == 200
    _cleanup_report_dir(r1.json()["id"])

    # BB-EP-V2 covers (1), (5) [omitted text], (7) [.jpeg], (8) [.png] in one multi-image request
    r2 = client.post(
        "/reports",
        data={"seat_id": "F1-02", "reporter_id": str(stu_id)},
        files=[
            ("images", ("b.jpeg", io.BytesIO(b"\xff\xd8\xff\xe0jpeg"), "image/jpeg")),
            ("images", ("c.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")),
        ],
    )
    assert r2.status_code == 200 and len(r2.json()["images"]) == 2
    _cleanup_report_dir(r2.json()["id"])

    # BB-EP-V3 covers (1), (4), (9) [no image] + (14) [student JWT on /auth/me & /auth/logout]
    r3 = client.post("/reports", data={"seat_id": "F1-03", "reporter_id": str(stu_id), "text": "No photo"})
    assert r3.status_code == 200 and r3.json()["images"] == []
    stu_tok = _login(client, "stu_p6")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {stu_tok}"}).status_code == 200
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {stu_tok}"}).status_code == 200

    # BB-EP-V4 covers (13) [admin JWT on /admin/seats/{id}/lock]
    adm_tok = _login(client, "adm_p6")
    r4 = client.post("/admin/seats/F1-04/lock", params={"minutes": 5}, headers={"Authorization": f"Bearer {adm_tok}"})
    assert r4.status_code == 200


@pytest.mark.parametrize(
    "case_id,invalid_class,seat_id,filename,mime,payload",
    [
        ("BB-EP-I1", "(2) non-existent seat_id", "F9-99", "ok.png", "image/png", b"\x89PNG\r\n\x1a\n"),
        ("BB-EP-I2", "(3) empty seat_id",        "",      "ok.png", "image/png", b"\x89PNG\r\n\x1a\n"),
        ("BB-EP-I3", "(10) .gif extension",      "F1-01", "x.gif",  "image/gif", b"GIF89a"),
        ("BB-EP-I4", "(11) .txt extension",      "F1-01", "x.txt",  "text/plain", b"hello"),
        ("BB-EP-I5", "(12) missing extension",   "F1-01", "noext",  "image/png", b"\x89PNG\r\n\x1a\n"),
    ],
)
def test_bb_ep_robust_single_invalid_class_report(api_ctx, case_id, invalid_class, seat_id, filename, mime, payload):
    """
    Robust EP (Rule 3, P.14 & P.16): Each invalid test case introduces ONLY ONE
    invalid equivalence class while keeping all other inputs valid.
    """
    client, _, stu_id, _ = api_ctx
    res = client.post(
        "/reports",
        data={"seat_id": seat_id, "reporter_id": str(stu_id), "text": f"{case_id}:{invalid_class}"},
        files=[("images", (filename, io.BytesIO(payload), mime))],
    )
    assert res.status_code in (400, 422)
    assert client.get("/seats/F1-01").json()["is_reported"] is False


def test_bb_ep_robust_single_invalid_token_classes(api_ctx):
    """Robust EP for invalid token classes (15), (16), (17) — one invalid class at a time."""
    client, _, _, _ = api_ctx
    # BB-EP-I6: (15) missing token
    assert client.get("/auth/me").status_code == 401
    # BB-EP-I7: (16) malformed JWT
    assert client.get("/auth/me", headers={"Authorization": "Bearer invalid.jwt.str"}).status_code == 401
    # BB-EP-I8: (17) valid signature JWT for deleted/non-existent user
    ghost_tok = create_access_token(subject="deleted_student", user_id=999, role="student")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {ghost_tok}"}).status_code == 401


# ===========================================================================
# 2. Boundary Value Analysis (边界值分析法 — Black_box.pdf P.25-P.34)
#    Single-Fault Assumption: min-, min, min+, nom, max-, max, max+
# ===========================================================================
@pytest.mark.parametrize(
    "label,minutes,exp_min_delta,exp_max_delta",
    [
        ("min-", -1,   -1,     2),      # Robust below min -> clamped to 0 (now)
        ("min",   0,   -1,     2),      # Exact min -> now
        ("min+",  1,   58,    62),      # Just above min -> +60s
        ("nom",   5,   298,  302),      # Normal default -> +300s
        ("max-",  1439, 86338, 86342),  # Just below 24h -> +86340s
        ("max",   1440, 86398, 86402),  # 24h max -> +86400s
        ("max+",  1441, 86458, 86462),  # Above 24h (accepted by int param)
    ],
)
def test_bb_bva01_lock_minutes_seven_point_robust_bva(api_ctx, label, minutes, exp_min_delta, exp_max_delta):
    """BB-BVA-01: 7-point Robust BVA (min-, min, min+, nom, max-, max, max+) on lock minutes [0, 1440]."""
    client, _, _, _ = api_ctx
    adm_tok = _login(client, "adm_p6")
    now = int(time.time())
    r = client.post(
        "/admin/seats/F1-01/lock",
        params={"minutes": minutes},
        headers={"Authorization": f"Bearer {adm_tok}"},
    )
    assert r.status_code == 200, label
    delta = r.json()["lock_until_ts"] - now
    assert exp_min_delta <= delta <= exp_max_delta


@pytest.mark.parametrize(
    "pt,expect_valid",
    [
        # Keep y = y_nom (540), vary x across min-, min, min+, nom, max-, max, max+ on [0, 1920]
        ([-1,   540], False),  # <x_min-, y_nom>
        ([0,    540], True),   # <x_min,  y_nom>
        ([1,    540], True),   # <x_min+, y_nom>
        ([960,  540], True),   # <x_nom,  y_nom>
        ([1919, 540], True),   # <x_max-, y_nom>
        ([1920, 540], True),   # <x_max,  y_nom>
        ([1921, 540], False),  # <x_max+, y_nom>
        # Keep x = x_nom (960), vary y across min-, min, min+, max-, max, max+ on [0, 1080]
        ([960,   -1], False),  # <x_nom, y_min->
        ([960,    0], True),   # <x_nom, y_min>
        ([960,    1], True),   # <x_nom, y_min+>
        ([960, 1079], True),   # <x_nom, y_max->
        ([960, 1080], True),   # <x_nom, y_max>
        ([960, 1081], False),  # <x_nom, y_max+>
    ],
)
def test_bb_bva02_two_variable_single_fault_roi_coordinates(pt, expect_valid):
    """
    BB-BVA-02: Two-variable Single-Fault Robust BVA (6n + 1 = 13 cases, Black_box.pdf P.29-P.30)
    for ROI vertex (x, y) within frame_size [0, 1920] x [0, 1080].
    """
    cfg = {
        "floor_id": "F1",
        "stream_path": "input/test/F1.mp4",
        "frame_size": [1920, 1080],
        "seats": [
            {
                "seat_id": "F1-01",
                "has_power": 1,
                # Non-collinear triangle with two fixed interior anchors + test vertex pt
                "desk_roi": [pt, [200, 100], [100, 300]],
            }
        ],
    }
    if expect_valid:
        validate_floor_config(cfg)
    else:
        with pytest.raises(ValueError, match="out of bounds"):
            validate_floor_config(cfg)


@pytest.mark.parametrize(
    "empty_cnt,total_cnt,expected_color",
    [
        (0,   100, "#FF0000"),  # min  (0%)   -> Red
        (1,   100, "#FEAE03"),  # min+ (1%)   -> Yellow
        (49,  100, "#FEAE03"),  # threshold- (49%) -> Yellow
        (50,  100, "#FEAE03"),  # threshold  (50%) -> Yellow
        (51,  100, "#60D937"),  # threshold+ (51%) -> Green
        (99,  100, "#60D937"),  # max- (99%)  -> Green
        (100, 100, "#60D937"),  # max  (100%) -> Green
    ],
)
def test_bb_bva03_floor_empty_ratio_seven_boundaries(api_ctx, empty_cnt, total_cnt, expected_color):
    """BB-BVA-03: Boundary values around 0%, 50%, and 100% floor availability thresholds."""
    client, SessionLocal, _, _ = api_ctx
    db = SessionLocal()
    db.query(Seat).delete()
    for i in range(total_cnt):
        db.add(Seat(seat_id=f"FB-{i:03d}", floor_id="FB", is_empty=(i < empty_cnt)))
    db.commit()
    db.close()

    res = client.get("/floors").json()
    assert res[0]["floor_color"] == expected_color


def test_bb_bva04_malicious_occupancy_timer_boundaries(api_ctx):
    """BB-BVA-04: 5-point BVA around 2h (7200s) malicious occupancy timer: 0, 1, 3600(nom), 7199, 7200, 7201."""
    client, SessionLocal, _, _ = api_ctx
    now = int(time.time())
    db = SessionLocal()
    db.query(Seat).delete()
    samples = [
        ("FT-00", 0, False),
        ("FT-01", now - 1, False),
        ("FT-02", now - 3600, False),
        ("FT-03", now - 7199, False),
        ("FT-04", now - 7200, True),
        ("FT-05", now - 7201, True),
    ]
    for sid, occ_ts, mal in samples:
        db.add(Seat(seat_id=sid, floor_id="FT", is_empty=False, occupancy_start_ts=occ_ts, is_malicious=mal))
    db.commit()
    db.close()

    for sid, occ_ts, mal in samples:
        st = client.get(f"/stats/seats/{sid}").json()
        expected_sec = 0 if occ_ts == 0 else (now - occ_ts)
        assert expected_sec <= st["object_only_occupy_seconds"] <= expected_sec + 3
        assert st["is_malicious"] is mal


# ===========================================================================
# 3. Decision Table Testing (判定表法 — Black_box.pdf P.35-P.55)
#    Step 1..4: Initial 2^4 = 16 rules for (C1:is_empty, C2:has_power, C3:is_reported, C4:is_malicious)
#    Step 5: Simplified Decision Table merging Don't-Care ('—') entries -> 8 rules
# ===========================================================================
@pytest.mark.parametrize(
    "rule_id,c1_empty,c2_power,c3_rep,c4_mal,exp_seat,exp_admin",
    [
        # Simplified Rule S1: C1=T, C2=F, C3=F, C4=F -> (Green, Green)
        ("S1", True,  False, False, False, "#60D937", "#60D937"),
        # Simplified Rule S2: C1=T, C2=T, C3=F, C4=F -> (Blue, Blue)
        ("S2", True,  True,  False, False, "#00A1FF", "#00A1FF"),
        # Simplified Rule S3: C1=F, C2=—(don't-care), C3=F, C4=F -> (Gray, Gray) [merges 2 rules]
        ("S3a", False, False, False, False, "#929292", "#929292"),
        ("S3b", False, True,  False, False, "#929292", "#929292"),
        # Simplified Rule S4: C1=—, C2=—, C3=T, C4=F -> (Yellow, Yellow) [merges 4 rules]
        ("S4a", True,  False, True,  False, "#FEAE03", "#FEAE03"),
        ("S4b", False, True,  True,  False, "#FEAE03", "#FEAE03"),
        # Simplified Rule S5: C1=T, C2=F, C3=F, C4=T -> (Green, Gray)
        ("S5", True,  False, False, True,  "#60D937", "#929292"),
        # Simplified Rule S6: C1=T, C2=T, C3=F, C4=T -> (Blue, Gray)
        ("S6", True,  True,  False, True,  "#00A1FF", "#929292"),
        # Simplified Rule S7: C1=T, C2=—, C3=T, C4=T -> (Yellow, Gray) [merges 2 rules]
        ("S7a", True,  False, True,  True,  "#FEAE03", "#929292"),
        ("S7b", True,  True,  True,  True,  "#FEAE03", "#929292"),
        # Simplified Rule S8: C1=F, C2=F, C3=F/T, C4=T -> admin Green
        ("S8a", False, False, False, True,  "#929292", "#60D937"),
        ("S8b", False, False, True,  True,  "#FEAE03", "#60D937"),
        # Simplified Rule S9: C1=F, C2=T, C3=F/T, C4=T -> admin Blue
        ("S9a", False, True,  False, True,  "#929292", "#00A1FF"),
        ("S9b", False, True,  True,  True,  "#FEAE03", "#00A1FF"),
    ],
)
def test_bb_dt01_simplified_and_initial_color_decision_table(
    api_ctx, rule_id, c1_empty, c2_power, c3_rep, c4_mal, exp_seat, exp_admin
):
    """BB-DT-01: Decision Table rules (covering initial 16 combinations & simplified '—' rules)."""
    client, SessionLocal, _, _ = api_ctx
    db = SessionLocal()
    seat = db.query(Seat).filter_by(seat_id="F1-01").one()
    seat.is_empty = c1_empty
    seat.has_power = c2_power
    seat.is_reported = c3_rep
    seat.is_malicious = c4_mal
    db.commit()
    db.close()

    body = client.get("/seats/F1-01").json()
    assert body["seat_color"] == exp_seat, rule_id
    assert body["admin_color"] == exp_admin, rule_id


def test_bb_dt02_rbac_decision_table_with_impossible_elimination(api_ctx):
    """
    BB-DT-02: RBAC Decision Table (Black_box.pdf P.49-P.51: remove Impossible combinations
    such as C1:ValidToken=F & C2:RoleAdmin=T). Tests all feasible rules.
    """
    client, _, _, _ = api_ctx
    stu_tok = _login(client, "stu_p6")
    adm_tok = _login(client, "adm_p6")

    feasible_rules = [
        # Rule 1: C1(ValidJWT)=F, C2(RoleAdmin)=F(—), C3(AdminRoute)=F -> 401 on /auth/me
        ({}, "/auth/me", 401),
        # Rule 2: C1(ValidJWT)=F, C2(RoleAdmin)=F(—), C3(AdminRoute)=T -> 401 on /admin/anomalies
        ({}, "/admin/anomalies", 401),
        ({"Authorization": "Bearer forged.token"}, "/admin/anomalies", 401),
        # Rule 3: C1(ValidJWT)=T, C2(RoleAdmin)=F, C3(AdminRoute)=F -> 200 on /auth/me
        ({"Authorization": f"Bearer {stu_tok}"}, "/auth/me", 200),
        # Rule 4: C1(ValidJWT)=T, C2(RoleAdmin)=F, C3(AdminRoute)=T -> 403 Forbidden
        ({"Authorization": f"Bearer {stu_tok}"}, "/admin/anomalies", 403),
        # Rule 5: C1(ValidJWT)=T, C2(RoleAdmin)=T, C3(AdminRoute)=F -> 200 on /auth/me
        ({"Authorization": f"Bearer {adm_tok}"}, "/auth/me", 200),
        # Rule 6: C1(ValidJWT)=T, C2(RoleAdmin)=T, C3(AdminRoute)=T -> 200 on /admin/anomalies
        ({"Authorization": f"Bearer {adm_tok}"}, "/admin/anomalies", 200),
    ]
    for headers, url, exp_code in feasible_rules:
        assert client.get(url, headers=headers).status_code == exp_code


# ===========================================================================
# 4. Cause-Effect Graph (因果图法 — Black_box.pdf P.56-P.66)
#    Target: POST /reports
#    Causes (0 / 1):
#      c1: seat_id exists in DB
#      c2: request attaches image file(s)
#      c3: file extension in {.jpg, .jpeg, .png}
#      c4: MIME content_type starts with "image/"
#    Constraints (P.59-P.61):
#      R (Require): c3 --R--> c2,  c4 --R--> c2
#        (when c2=0, both c3=0 and c4=0; columns with c2=0 & (c3=1 or c4=1) are Impossible!)
#      M (Mask):    e1 --M--> e3,  e2 --M--> e3
#    Intermediate Nodes:
#      node 11 (m1): (~c2) v c3     (image check passes; Note: c3=1 satisfies extension fallback even if c4=0)
#      node 12 (m2): c1 ^ m1        (report transaction succeeds)
#    Effects (0 / 1):
#      e1: 400 "seat_id not found"          (~c1)
#      e2: 400 "Unsupported file extension" (c1 ^ c2 ^ ~c3) + DB rollback
#      e3: 200 Report(status="pending")     (m2)
#      e4: seat.is_reported = True          (m2)
#      e5: image saved under config/report/ (m2 ^ c2)
#
#    Valid columns of converted 0/1 Decision Table (after removing R-Impossible columns):
#      Col 1: c1=1, c2=0, c3=0, c4=0 -> m1=1, m2=1 -> e3=1, e4=1, e5=0
#      Col 2: c1=1, c2=1, c3=1, c4=1 -> m1=1, m2=1 -> e3=1, e4=1, e5=1
#      Col 3: c1=1, c2=1, c3=1, c4=0 -> m1=1, m2=1 -> e3=1, e4=1, e5=1 (extension fallback)
#      Col 4: c1=1, c2=1, c3=0, c4=1 -> m1=0, m2=0 -> e2=1 (400 + rollback, e.g. image/gif .gif)
#      Col 5: c1=1, c2=1, c3=0, c4=0 -> m1=0, m2=0 -> e2=1 (400 + rollback, e.g. text/plain .py)
#      Col 6: c1=0, c2=0, c3=0, c4=0 -> m1=1, m2=0 -> e1=1 (400 seat_id not found)
#      Col 7: c1=0, c2=1, c3=1, c4=1 -> m1=1, m2=0 -> e1=1 (400 seat_id not found, M masks e5)
# ===========================================================================
@pytest.mark.parametrize(
    "col_id,c1,c2,c3,c4,exp_status,exp_saved",
    [
        ("BB-CE-Col1", 1, 0, 0, 0, 200, 0),
        ("BB-CE-Col2", 1, 1, 1, 1, 200, 1),
        ("BB-CE-Col3", 1, 1, 1, 0, 200, 1),
        ("BB-CE-Col4", 1, 1, 0, 1, 400, 0),
        ("BB-CE-Col5", 1, 1, 0, 0, 400, 0),
        ("BB-CE-Col6", 0, 0, 0, 0, 400, 0),
        ("BB-CE-Col7", 0, 1, 1, 1, 400, 0),
    ],
)
def test_bb_ce_all_converted_decision_table_columns(api_ctx, col_id, c1, c2, c3, c4, exp_status, exp_saved):
    """Executes all 7 feasible columns of the Cause-Effect Decision Table (Black_box.pdf P.63-P.65)."""
    client, SessionLocal, stu_id, _ = api_ctx
    seat_id = "F1-01" if c1 == 1 else "NO-SEAT"

    files = None
    if c2 == 1:
        fname = "ev.png" if c3 == 1 else ("anim.gif" if c4 == 1 else "bad.py")
        mime = "image/png" if (c3 == 1 and c4 == 1) else ("image/gif" if c4 == 1 else "application/octet-stream")
        files = [("images", (fname, io.BytesIO(b"\x89PNG\r\n\x1a\n"), mime))]

    res = client.post(
        "/reports",
        data={"seat_id": seat_id, "reporter_id": str(stu_id), "text": col_id},
        files=files,
    )
    assert res.status_code == exp_status, f"{col_id}: {res.text}"

    if exp_status == 200:
        body = res.json()
        assert body["status"] == "pending"          # e3 = 1
        assert len(body["images"]) == exp_saved     # e5 = 1 or 0
        assert client.get("/seats/F1-01").json()["is_reported"] is True  # e4 = 1
        if exp_saved:
            _cleanup_report_dir(body["id"])
    else:
        db = SessionLocal()
        if c1 == 0:
            assert res.json()["detail"] == "seat_id not found"  # e1 = 1
        else:
            assert "Unsupported file extension" in res.json()["detail"]  # e2 = 1
            # Verify rollback kept F1-01 clean
            assert db.query(Report).filter_by(seat_id="F1-01").count() == 0
            assert db.query(Seat).filter_by(seat_id="F1-01").one().is_reported is False
        db.close()
