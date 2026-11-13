# -*- coding: utf-8 -*-
"""
Part 6 White-Box Test Suite for Library Seat Management System.

Implements both required white-box testing methods:
1. Logical Covering Method (逻辑覆盖法: 语句/判定/条件/判定-条件/条件组合/MC-DC):
   WB-LC-01 .. WB-LC-04
2. Basic Path Method (基本路径法: 控制流图 CFG -> 圈复杂度 V(G) -> 独立路径集):
   WB-BP-01 .. WB-BP-04
"""
from __future__ import annotations

import io
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.auth import create_access_token, get_current_user, get_password_hash, require_admin
from backend.db import Base
from backend.models import Report, Seat, User
from backend.routes import admin as admin_routes
from backend.routes import reports as report_routes
from backend.services import rollover, yolo_service
from backend.services.color import (
    ADMIN_YELLOW,
    FLOOR_RED,
    SEAT_BLUE,
    SEAT_GRAY,
    SEAT_GREEN,
    compute_admin_color,
    compute_floor_color,
    compute_seat_color,
)
from backend.services.yolo_service import Detection, point_in_polygon, refresh_floor


def _new_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


# ===========================================================================
# 1. Logical Covering Method (逻辑覆盖法)
# ===========================================================================
def test_wb_lc01_color_service_full_logic_and_mcdc():
    """
    WB-LC-01: Statement / Branch / Condition / Multiple-Condition / MC-DC on color.py.
    Targets:
      - compute_seat_color(is_empty, has_power, is_reported)
      - compute_admin_color(base_color, is_malicious, is_empty, has_power)
      - compute_floor_color(empty_count, total_count)
    """
    # Multiple-condition table for compute_seat_color (8 combinations of 3 booleans)
    expected_seat = {
        (False, False, False): SEAT_GRAY,
        (False, True,  False): SEAT_GRAY,
        (True,  False, False): SEAT_GREEN,
        (True,  True,  False): SEAT_BLUE,
        (False, False, True):  ADMIN_YELLOW,
        (False, True,  True):  ADMIN_YELLOW,
        (True,  False, True):  ADMIN_YELLOW,
        (True,  True,  True):  ADMIN_YELLOW,
    }
    for (is_empty, has_power, is_reported), exp in expected_seat.items():
        assert compute_seat_color(is_empty, has_power, is_reported) == exp

    # Full condition combinations for compute_admin_color (is_malicious x is_empty x has_power)
    for is_malicious in (False, True):
        for is_empty in (False, True):
            for has_power in (False, True):
                base = compute_seat_color(is_empty, has_power, False)
                res = compute_admin_color(base, is_malicious, is_empty, has_power)
                if not is_malicious:
                    assert res == base
                elif is_empty:
                    assert res == SEAT_GRAY
                else:
                    assert res == (SEAT_BLUE if has_power else SEAT_GREEN)

    # compute_floor_color boundaries & branches
    assert compute_floor_color(0, 0) == FLOOR_RED
    assert compute_floor_color(0, 4) == FLOOR_RED
    assert compute_floor_color(2, 4) == ADMIN_YELLOW  # 0.5 is NOT > 0.5
    assert compute_floor_color(3, 4) == SEAT_GREEN    # 0.75 > 0.5


def test_wb_lc02_list_anomalies_mcdc():
    """
    WB-LC-02: MC/DC on admin.py:22-24:
      C1: Seat.is_reported == True
      C2: Seat.is_malicious == True
      Decision: (C1 or C2), plus C3: floor is not None
    """
    db = _new_db()
    db.add_all(
        [
            Seat(seat_id="F1-01", floor_id="F1", is_reported=False, is_malicious=False),  # (F, F) -> excluded
            Seat(seat_id="F1-02", floor_id="F1", is_reported=True,  is_malicious=False),  # (T, F) -> included
            Seat(seat_id="F1-03", floor_id="F1", is_reported=False, is_malicious=True),   # (F, T) -> included
            Seat(seat_id="F2-01", floor_id="F2", is_reported=True,  is_malicious=True),   # (T, T) -> included
        ]
    )
    db.commit()

    all_anoms = admin_routes.list_anomalies(floor=None, db=db)
    assert {a.seat_id for a in all_anoms} == {"F1-02", "F1-03", "F2-01"}

    f1_anoms = admin_routes.list_anomalies(floor="F1", db=db)
    assert {a.seat_id for a in f1_anoms} == {"F1-02", "F1-03"}
    db.close()


def test_wb_lc03_refresh_floor_conditions_and_lock_mcdc(monkeypatch: pytest.MonkeyPatch):
    """
    WB-LC-03: Multiple-Condition & MC/DC on yolo_service.py:341-370:
      - (person_present, object_present) all 4 combinations: (F,F), (T,F), (F,T), (T,T)
      - object_present and not person_present -> occupancy_start_ts start / keep / reset
      - now >= seat.lock_until_ts (locked vs unlocked)
      - seat.occupancy_start_ts and (now - seat.occupancy_start_ts) >= 7200
    """
    cfg = {
        "floor_id": "F1",
        "stream_path": "dummy.mp4",
        "seats": [
            {"seat_id": "F1-01", "has_power": 0, "desk_roi": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            {"seat_id": "F1-02", "has_power": 1, "desk_roi": [[200, 0], [300, 0], [300, 100], [200, 100]]},
            {"seat_id": "F1-03", "has_power": 0, "desk_roi": [[400, 0], [500, 0], [500, 100], [400, 100]]},
            {"seat_id": "F1-04", "has_power": 1, "desk_roi": [[600, 0], [700, 0], [700, 100], [600, 100]]},
        ],
    }

    fake_cap = MagicMock()
    fake_cap.isOpened.return_value = True
    fake_cap.read.return_value = (True, MagicMock())
    fake_vstate = yolo_service.VideoState(cap=fake_cap, total_frames=10, fps=2.0, next_frame_idx=0, stream_path="dummy.mp4")
    monkeypatch.setattr(yolo_service, "_open_or_get_video_state", lambda fid, sp: fake_vstate)

    fake_det = MagicMock()
    fake_det.person_name = "person"
    fake_det.object_names = {"backpack"}
    # F1-01: (F, F) empty; F1-02: (T, F) person; F1-03: (F, T) object-only; F1-04: (T, T) person+object
    fake_det.detect_frame.return_value = [
        Detection(240, 40, 260, 60, 0.9, "person"),
        Detection(440, 40, 460, 60, 0.9, "backpack"),
        Detection(640, 40, 660, 60, 0.9, "person"),
        Detection(640, 40, 660, 60, 0.9, "backpack"),
    ]
    monkeypatch.setattr(yolo_service, "get_detector", lambda: fake_det)

    db = _new_db()
    now = int(time.time())
    # Lock F1-01 in the future with is_empty=False -> locked seat must NOT change visual state
    db.add(Seat(seat_id="F1-01", floor_id="F1", is_empty=False, lock_until_ts=now + 600, last_update_ts=now - 5))
    # F1-03 already had object-only starting 7300s ago -> triggers is_malicious=True
    db.add(Seat(seat_id="F1-03", floor_id="F1", is_empty=True, occupancy_start_ts=now - 7300, last_update_ts=now - 5))
    # F1-04 had occupancy_start_ts before -> person+object resets occupancy_start_ts to 0
    db.add(Seat(seat_id="F1-04", floor_id="F1", is_empty=False, occupancy_start_ts=now - 100, last_update_ts=now - 5))
    db.commit()

    res = {s.seat_id: s for s in refresh_floor(db, cfg)}
    # F1-01 is locked, so visual is_empty stays False despite (F, F) observed empty; stats still track last_state_is_empty=True
    assert res["F1-01"].is_empty is False
    assert res["F1-01"].last_state_is_empty is True
    # F1-02 (T, F) -> occupied, occupancy_start_ts == 0
    assert res["F1-02"].is_empty is False
    assert res["F1-02"].occupancy_start_ts == 0
    # F1-03 (F, T) -> occupied & > 7200s -> is_malicious=True
    assert res["F1-03"].is_empty is False
    assert res["F1-03"].is_malicious is True
    # F1-04 (T, T) -> occupied & occupancy_start_ts reset to 0
    assert res["F1-04"].is_empty is False
    assert res["F1-04"].occupancy_start_ts == 0
    db.close()


def test_wb_lc04_rollover_condition_coverage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    WB-LC-04: Condition coverage on rollover.perform_rollovers_if_needed (lines 160-177):
      1. No non-zero last_update_ts -> early return
      2. Same month & same day -> no export
      3. Same month & different day -> daily export only
      4. Different month -> monthly export + daily export
    """
    monkeypatch.setattr(rollover, "OUTPUTS_DIR", tmp_path)
    db = _new_db()

    # Case 1: last_update_ts=0 -> early return
    db.add(Seat(seat_id="F1-01", floor_id="F1", last_update_ts=0))
    db.commit()
    rollover.perform_rollovers_if_needed(db, int(datetime(2025, 10, 15, 10, 0, tzinfo=timezone.utc).timestamp()))
    assert list(tmp_path.iterdir()) == []

    # Case 2: same local date -> no export
    t_same = datetime(2025, 10, 15, 9, 0, tzinfo=timezone.utc).astimezone()
    s = db.query(Seat).filter_by(seat_id="F1-01").one()
    s.last_update_ts = int(t_same.timestamp())
    s.daily_empty_seconds = 120
    s.total_empty_seconds = 500
    db.commit()
    rollover.perform_rollovers_if_needed(db, int(t_same.replace(hour=18).timestamp()))
    assert list(tmp_path.iterdir()) == []

    # Case 3: same month, next day -> daily_empty.txt created, total_empty_seconds preserved
    t_next_day = t_same.replace(day=16, hour=8)
    rollover.perform_rollovers_if_needed(db, int(t_next_day.timestamp()))
    assert (tmp_path / "2025-10-15" / "daily_empty.txt").exists()
    assert not (tmp_path / "monthly" / "2025-10.txt").exists()
    db.refresh(s)
    assert s.daily_empty_seconds == 0
    assert s.total_empty_seconds == 500
    db.close()


# ===========================================================================
# 2. Basic Path Method (基本路径法)
# ===========================================================================
def test_wb_bp01_compute_floor_color_basis_paths():
    """
    WB-BP-01: Basis Path Testing for color.compute_floor_color (color.py:30-38).
    CFG: P = 3 decision nodes (`total_count == 0`, `ratio == 0`, `ratio > 0.5`)
    Cyclomatic Complexity V(G) = P + 1 = 4 independent paths:
      Path 1: total_count == 0 -> FLOOR_RED
      Path 2: total_count != 0 -> ratio == 0 -> FLOOR_RED
      Path 3: total_count != 0 -> ratio != 0 -> ratio > 0.5 -> SEAT_GREEN
      Path 4: total_count != 0 -> ratio != 0 -> ratio <= 0.5 -> ADMIN_YELLOW
    """
    assert compute_floor_color(0, 0) == FLOOR_RED      # Path 1
    assert compute_floor_color(0, 10) == FLOOR_RED     # Path 2
    assert compute_floor_color(6, 10) == SEAT_GREEN    # Path 3
    assert compute_floor_color(5, 10) == ADMIN_YELLOW  # Path 4


def test_wb_bp02_point_in_polygon_basis_paths():
    """
    WB-BP-02: Basis Path Testing for yolo_service.point_in_polygon (yolo_service.py:193-207).
    V(G) = 4 independent paths:
      Path 1: empty polygon (loop 0 times) -> False
      Path 2: loop runs, intersect always False -> False
      Path 3: loop runs, intersect True odd times (inside=True) -> True
      Path 4: loop runs, intersect True even times (point to right of square) -> False
    """
    square = [[10.0, 10.0], [20.0, 10.0], [20.0, 20.0], [10.0, 20.0]]
    assert point_in_polygon((15.0, 15.0), []) is False      # Path 1
    assert point_in_polygon((5.0, 5.0), square) is False    # Path 2
    assert point_in_polygon((15.0, 15.0), square) is True   # Path 3
    assert point_in_polygon((25.0, 15.0), square) is False  # Path 4


def test_wb_bp03_save_report_images_basis_paths(tmp_path: Path):
    """
    WB-BP-03: Basis Path Testing for reports._save_report_images (reports.py:18-95).
    Key independent paths:
      Path 1: files=None -> return []
      Path 2: valid image/png + .png -> saved successfully
      Path 3: generic MIME application/octet-stream + .jpg -> extension fallback succeeds
      Path 4: unsupported extension .exe -> raises HTTPException(400)
      Path 5: underlying file read/write error -> propagates OSError
    """
    # Path 1
    assert report_routes._save_report_images(99001, None) == []

    # Path 2
    up_png = UploadFile(filename="a.png", file=io.BytesIO(b"\x89PNG\r\n\x1a\n"))
    # Set content_type via headers mock
    up_png = UploadFile(filename="a.png", file=io.BytesIO(b"\x89PNG\r\n\x1a\n"), headers={"content-type": "image/png"})
    saved2 = report_routes._save_report_images(99002, [up_png])
    assert len(saved2) == 1 and saved2[0].endswith(".png")

    # Path 3 (extension fallback)
    up_web = UploadFile(
        filename="b.jpg",
        file=io.BytesIO(b"\xff\xd8\xff\xe0"),
        headers={"content-type": "application/octet-stream"},
    )
    saved3 = report_routes._save_report_images(99003, [up_web])
    assert len(saved3) == 1 and saved3[0].endswith(".jpg")

    # Path 4 (invalid extension)
    up_bad = UploadFile(
        filename="evil.exe",
        file=io.BytesIO(b"MZ"),
        headers={"content-type": "application/octet-stream"},
    )
    with pytest.raises(HTTPException) as exc:
        report_routes._save_report_images(99004, [up_bad])
    assert exc.value.status_code == 400

    # Path 5 (I/O exception during f.file.read())
    broken_file = MagicMock()
    broken_file.filename = "c.png"
    broken_file.content_type = "image/png"
    broken_file.file.read.side_effect = OSError("disk read error")
    with pytest.raises(OSError, match="disk read error"):
        report_routes._save_report_images(99005, [broken_file])

    # Clean up temporary report folders
    import shutil
    for rid in (99002, 99003, 99004, 99005):
        p = BACKEND_ROOT / "config" / "report" / str(rid)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)


def test_wb_bp04_auth_and_require_admin_basis_paths():
    """
    WB-BP-04: Basis Path Testing for auth.get_current_user & require_admin (auth.py:41-64).
    V(G) = 5 independent paths:
      Path 1: invalid JWT -> JWTError -> 401
      Path 2: valid JWT missing 'sub' -> 401
      Path 3: valid JWT with unknown username -> 401
      Path 4: valid student user -> get_current_user succeeds, require_admin -> 403
      Path 5: valid admin user -> require_admin returns User
    """
    from jose import jwt
    from backend.auth import ALGORITHM, SECRET_KEY

    db = _new_db()
    stu = User(username="s1", pass_hash=get_password_hash("123456"), role="student")
    adm = User(username="a1", pass_hash=get_password_hash("123456"), role="admin")
    db.add_all([stu, adm])
    db.commit()
    db.refresh(stu)
    db.refresh(adm)

    # Path 1: bad JWT
    with pytest.raises(HTTPException) as e1:
        get_current_user(token="bad.jwt", db=db)
    assert e1.value.status_code == 401

    # Path 2: JWT without 'sub'
    no_sub_tok = jwt.encode({"uid": 1, "role": "student"}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(HTTPException) as e2:
        get_current_user(token=no_sub_tok, db=db)
    assert e2.value.status_code == 401

    # Path 3: non-existent user
    ghost_tok = create_access_token(subject="nobody", user_id=999, role="student")
    with pytest.raises(HTTPException) as e3:
        get_current_user(token=ghost_tok, db=db)
    assert e3.value.status_code == 401

    # Path 4: student fails require_admin
    stu_tok = create_access_token(subject="s1", user_id=stu.id, role="student")
    stu_user = get_current_user(token=stu_tok, db=db)
    with pytest.raises(HTTPException) as e4:
        require_admin(user=stu_user)
    assert e4.value.status_code == 403

    # Path 5: admin passes require_admin
    adm_tok = create_access_token(subject="a1", user_id=adm.id, role="admin")
    adm_user = get_current_user(token=adm_tok, db=db)
    assert require_admin(user=adm_user).username == "a1"
    db.close()
