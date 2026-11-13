from __future__ import annotations

import socket
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from .auth import get_password_hash
from .db import Base, SessionLocal, engine
from .models import Seat, User
from .routes import admin as admin_routes
from .routes import auth as auth_routes
from .routes import health as health_routes
from .routes import reports as reports_routes
from .routes import seats as seats_routes
from .scheduler import FloorRefreshScheduler
from .services.roi_loader import list_floor_ids, load_floor_config


def _detect_lan_ip() -> str:
	try:
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
			s.connect(("8.8.8.8", 80))
			return s.getsockname()[0]
	except Exception:
		return "127.0.0.1"


def _seed_defaults_if_needed() -> None:
	db = SessionLocal()
	try:
		if not db.query(User).filter(User.username == "admin").first():
			db.add(User(username="admin", pass_hash=get_password_hash("123456"), role="admin"))
		if not db.query(User).filter(User.username == "user").first():
			db.add(User(username="user", pass_hash=get_password_hash("123456"), role="student"))
		db.commit()

		for floor_id in list_floor_ids():
			try:
				cfg = load_floor_config(floor_id)
				existing = {s.seat_id for s in db.query(Seat).filter(Seat.floor_id == floor_id).all()}
				for s in cfg.get("seats", []):
					if s["seat_id"] not in existing:
						db.add(
							Seat(
								seat_id=s["seat_id"],
								floor_id=floor_id,
								has_power=bool(s.get("has_power", 0)),
								is_empty=True,
							)
						)
				db.commit()
			except Exception:
				db.rollback()
	except Exception:
		db.rollback()
	finally:
		db.close()


def create_app() -> FastAPI:
	app = FastAPI(title="Library Seat Backend", version="0.1.0")

	# CORS Configuration
	app.add_middleware(
		CORSMiddleware,
		allow_origins=["*"],  # Allows all origins
		allow_credentials=True,
		allow_methods=["*"],  # Allows all methods
		allow_headers=["*"],  # Allows all headers
	)

	# Include routers
	app.include_router(health_routes.router)
	app.include_router(auth_routes.router)
	app.include_router(seats_routes.router)
	app.include_router(reports_routes.router)
	app.include_router(admin_routes.router)

	# Static files for report images
	base_dir = Path(__file__).resolve().parents[1]
	project_root = base_dir.parent
	report_dir = base_dir / "config" / "report"
	report_dir.mkdir(parents=True, exist_ok=True)
	app.mount("/report", StaticFiles(directory=report_dir.as_posix()), name="report")

	# Mount Flutter Web build at /app if built
	web_build_dir = project_root / "FRONTEND" / "build" / "web"
	if web_build_dir.exists():
		app.mount("/app", StaticFiles(directory=web_build_dir.as_posix(), html=True), name="web_app")

	dist_dir = project_root / "dist"

	@app.get("/", response_class=HTMLResponse, include_in_schema=False)
	@app.get("/download", response_class=HTMLResponse, include_in_schema=False)
	def wifi_download_portal(request: Request) -> HTMLResponse:
		lan_ip = _detect_lan_ip()
		host_header = request.headers.get("host") or f"{lan_ip}:8000"
		base_url = f"http://{host_header}"
		win_zip = dist_dir / "LibrarySeat_Windows_App.zip"
		apk_file = dist_dir / "LibrarySeat.apk"
		web_ready = (web_build_dir / "index.html").exists()

		win_btn = (
			f'<a class="btn primary" href="/download/windows">下载 Windows 桌面版 (.zip, {win_zip.stat().st_size // (1024*1024)} MB)</a>'
			if win_zip.exists()
			else '<span class="btn disabled">Windows 桌面版打包中...</span>'
		)
		apk_btn = (
			f'<a class="btn apk" href="/download/android">下载 Android 手机版 (.apk, {apk_file.stat().st_size // (1024*1024)} MB)</a>'
			if apk_file.exists()
			else ""
		)
		web_btn = (
			'<a class="btn web" href="/app/">直接在线打开网页版 App（手机/电脑免安装）</a>'
			if web_ready
			else ""
		)

		html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Library Seat Management — 局域网下载与在线入口</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#eef2f7; margin:0; padding:24px; color:#1e293b; }}
    .card {{ max-width:560px; margin:24px auto; background:#fff; border-radius:20px; padding:28px; box-shadow:0 10px 28px rgba(15,23,42,.08); }}
    h1 {{ margin:0 0 8px; font-size:22px; color:#0f172a; }}
    .tag {{ display:inline-block; background:#dcfce7; color:#166534; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:600; margin-bottom:16px; }}
    .btn {{ display:block; text-align:center; padding:14px 18px; border-radius:12px; text-decoration:none; font-weight:600; margin:12px 0; font-size:15px; }}
    .primary {{ background:#2563eb; color:#fff; }}
    .web {{ background:#16a34a; color:#fff; }}
    .apk {{ background:#0d9488; color:#fff; }}
    .disabled {{ background:#cbd5e1; color:#475569; }}
    .box {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; font-size:13.5px; line-height:1.65; margin-top:16px; }}
    code {{ background:#e2e8f0; padding:2px 6px; border-radius:6px; font-size:13px; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="tag">同一 Wi-Fi 局域网直连已就绪</span>
    <h1>Library Seat Management System</h1>
    <p style="color:#475569;font-size:14px;margin-top:4px;">
      同学在同一 Wi-Fi 下访问 <code>http://{lan_ip}:8000</code> 即可直接在线使用或下载客户端。
    </p>
    {web_btn}
    {win_btn}
    {apk_btn}
    <div class="box">
      <strong>默认测试账号：</strong><br/>
      • 学生端：账号 <code>user</code> &nbsp; 密码 <code>123456</code><br/>
      • 管理员：账号 <code>admin</code> &nbsp; 密码 <code>123456</code><br/>
      • 当前服务器地址：<code>{base_url}</code><br/>
      • API 文档：<a href="/docs">{base_url}/docs</a>
    </div>
  </div>
</body>
</html>"""
		return HTMLResponse(content=html)

	@app.get("/download/windows", include_in_schema=False)
	def download_windows_zip():
		win_zip = dist_dir / "LibrarySeat_Windows_App.zip"
		if not win_zip.exists():
			return JSONResponse({"detail": "Windows package not built yet"}, status_code=404)
		return FileResponse(
			path=win_zip.as_posix(),
			filename="LibrarySeat_Windows_App.zip",
			media_type="application/zip",
		)

	@app.get("/download/android", include_in_schema=False)
	def download_android_apk():
		apk_file = dist_dir / "LibrarySeat.apk"
		if not apk_file.exists():
			return JSONResponse({"detail": "Android APK not built yet"}, status_code=404)
		return FileResponse(
			path=apk_file.as_posix(),
			filename="LibrarySeat.apk",
			media_type="application/vnd.android.package-archive",
		)

	# Create tables on startup
	@app.on_event("startup")
	def on_startup():
		Base.metadata.create_all(bind=engine)
		_seed_defaults_if_needed()
		# 后台预加载 YOLO 模型，避免登录后第一轮检测卡在加载权重上
		def _warmup() -> None:
			try:
				from .services.yolo_service import get_detector
				get_detector()
			except Exception:
				pass
		import threading
		threading.Thread(target=_warmup, daemon=True).start()
		# 创建调度器但不启动，等待用户登录后再启动
		app.state.scheduler = FloorRefreshScheduler()

	@app.on_event("shutdown")
	def on_shutdown():
		sched = getattr(app.state, "scheduler", None)
		if sched:
			sched.shutdown()

	return app


app = create_app()
