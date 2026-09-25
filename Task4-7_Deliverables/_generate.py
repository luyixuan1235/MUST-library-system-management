# -*- coding: utf-8 -*-
"""Generate Task 4-7 deliverables: use-case diagram (PNG) + Word document."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Rectangle, Circle
import matplotlib.lines as mlines

BASE = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(BASE, "use_case_diagram.png")

# ----------------------------------------------------------------------------
# 1. USE-CASE DIAGRAM
# ----------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(16.5, 11.5), dpi=150)
ax.set_xlim(-0.3, 16.5)
ax.set_ylim(-0.6, 14.2)
ax.axis("off")

LX, RX = 5.5, 11.0   # left / right use-case columns
MX = 8.25            # middle column
EW, EH = 3.4, 0.95   # ellipse size

ucs = {
    # id: (x, y, label)
    "UC1":  (LX, 13.2, "Register Account"),
    "UC2":  (LX, 11.9, "Log In / Log Out"),
    "UC3":  (LX, 10.6, "View Floor Map &\nSeat Status"),
    "UC4":  (LX, 9.3,  "View Seat Details /\nStatistics"),
    "UC5":  (LX, 7.7,  "Report Seat Issue"),
    "UC6":  (LX, 6.3,  "Upload Photo Evidence"),
    "UC7":  (LX, 5.0,  "Switch Language"),
    "UC8":  (RX, 11.9, "View Anomaly List"),
    "UC9":  (RX, 10.6, "View Report Details\n& Images"),
    "UC10": (RX, 9.3,  "Confirm / Dismiss\nAnomaly"),
    "UC11": (RX, 7.9,  "Clear Anomaly"),
    "UC12": (RX, 6.6,  "Lock Seat (5 min)"),
    "UC13": (RX, 5.3,  "Trigger Floor\nRefresh"),
    "UC14": (MX, 13.2, "Detect Seat Occupancy\n(YOLOv11)"),
    "UC15": (MX, 11.9, "Raise System Auto-Alarm\n(Malicious Occupancy)"),
    "UC16": (MX, 10.6, "Export Daily/Monthly\nStatistics"),
}

# System boundary
box = Rectangle((3.4, 4.2), 9.7, 10.2, fill=False, lw=2.0, edgecolor="#222222")
ax.add_patch(box)
ax.text(8.25, 14.15, "Library Seat Management System", ha="center", va="bottom",
        fontsize=14, fontweight="bold")

# Use cases
for (x, y, label) in ucs.values():
    ax.add_patch(Ellipse((x, y), EW, EH, fill=True, facecolor="#EAF3FF",
                         edgecolor="#1F5AA8", lw=1.6))
    ax.text(x, y, label, ha="center", va="center", fontsize=9.3)

def stick(x, y, name, sub=""):
    """Draw an actor stick figure centered at (x, y)."""
    ax.add_patch(Circle((x, y + 0.62), 0.26, fill=False, lw=2.0, edgecolor="#111111"))
    ax.plot([x, x], [y + 0.36, y - 0.28], color="#111111", lw=2.0)          # body
    ax.plot([x - 0.42, x + 0.42], [y + 0.12, y + 0.12], color="#111111", lw=2.0)  # arms
    ax.plot([x, x - 0.34], [y - 0.28, y - 0.78], color="#111111", lw=2.0)   # legs
    ax.plot([x, x + 0.34], [y - 0.28, y - 0.78], color="#111111", lw=2.0)
    ax.text(x, y - 1.12, name, ha="center", va="top", fontsize=11.5, fontweight="bold")
    if sub:
        ax.text(x, y - 1.52, sub, ha="center", va="top", fontsize=8.5, color="#555555")

def line(p1, p2):
    ax.annotate("", xy=p2, xytext=p1,
                arrowprops=dict(arrowstyle="-", color="#333333", lw=1.3))

def darrow(p1, p2, label, lab_xy=None, rotate=False):
    ax.annotate("", xy=p2, xytext=p1,
                arrowprops=dict(arrowstyle="->", color="#7A1FA2", lw=1.3,
                                linestyle=(0, (5, 3))))
    if lab_xy is None:
        lab_xy = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    ax.text(lab_xy[0], lab_xy[1], label, ha="center", va="center", fontsize=8.3,
            color="#7A1FA2", style="italic",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))

def anchor(uc_id, side):
    x, y, _ = ucs[uc_id]
    return {"l": (x - EW / 2, y), "r": (x + EW / 2, y),
            "t": (x, y + EH / 2), "b": (x, y - EH / 2)}[side]

# Actors
stick(1.15, 8.6, "Student", "(Library User)")
stick(15.35, 8.6, "Administrator", "(Library Staff)")
stick(15.35, 13.0, "System Scheduler", "(Timer, internal trigger)")
stick(1.15, 13.0, "Camera /\nVideo Stream", "(per-floor surveillance)")

# Student associations
for uc in ["UC1", "UC2", "UC3", "UC4", "UC5", "UC7"]:
    line((1.62, 8.75), anchor(uc, "l"))
# Admin associations
for uc in ["UC8", "UC9", "UC10", "UC11", "UC12", "UC13"]:
    line((14.88, 8.75), anchor(uc, "r"))
# Camera & scheduler
line((1.75, 13.0), anchor("UC14", "l"))
line((14.75, 13.2), anchor("UC14", "r"))
line((14.75, 12.4), anchor("UC15", "r"))
line((14.75, 10.6), (12.0, 10.6))
line((12.0, 10.6), anchor("UC16", "r"))

# include / extend
darrow(anchor("UC3", "t"), anchor("UC2", "b"), "\u00abinclude\u00bb")
darrow(anchor("UC5", "t"), (LX, 11.9 + EH / 2 + 0.45), "\u00abinclude\u00bb")
line((LX, 11.9 + EH / 2 + 0.45), (LX, 11.9 + EH / 2))  # small helper segment
darrow(anchor("UC5", "b"), anchor("UC6", "t"), "\u00abinclude\u00bb")
darrow(anchor("UC10", "r"), anchor("UC8", "r"), "\u00abextend\u00bb",
       lab_xy=(RX + 2.05, 9.95))
darrow(anchor("UC11", "r"), anchor("UC8", "r"), "\u00abextend\u00bb",
       lab_xy=(RX + 2.35, 8.6))
darrow(anchor("UC12", "r"), anchor("UC8", "r"), "\u00abextend\u00bb",
       lab_xy=(RX + 2.05, 7.25))
darrow(anchor("UC15", "l"), anchor("UC14", "l"), "\u00abextend\u00bb",
       lab_xy=(MX - 2.2, 12.55))
darrow(anchor("UC9", "t"), anchor("UC8", "b"), "\u00abinclude\u00bb")

# Legend
ax.plot([0.2, 1.0], [2.6, 2.6], color="#333333", lw=1.3)
ax.text(1.15, 2.6, "association", fontsize=9, va="center")
ax.annotate("", xy=(4.6, 2.6), xytext=(3.6, 2.6),
            arrowprops=dict(arrowstyle="->", color="#7A1FA2", lw=1.3,
                            linestyle=(0, (5, 3))))
ax.text(4.75, 2.6, "\u00abinclude\u00bb / \u00abextend\u00bb dependency", fontsize=9, va="center")
ax.text(0.2, 1.9, "Note: Detect Seat Occupancy runs automatically every 8 s per floor; "
        "Auto-Alarm flags seats occupied by objects (no person) for > 2 h.",
        fontsize=8.5, color="#555555", va="center")

plt.tight_layout()
plt.savefig(PNG, bbox_inches="tight", facecolor="white")
plt.close()
print("Diagram saved:", PNG)

# ----------------------------------------------------------------------------
# 2. WORD DOCUMENT
# ----------------------------------------------------------------------------
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

doc = Document()

# base styles
st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(10.5)
for i, sz, color in [(1, 16, "1F5AA8"), (2, 13, "1F5AA8"), (3, 11.5, "333333")]:
    h = doc.styles[f"Heading {i}"]
    h.font.name = "Calibri"
    h.font.size = Pt(sz)
    h.font.color.rgb = RGBColor.from_string(color)
    h.font.bold = True

def p(text="", bold=False, italic=False, size=None, space_after=6):
    par = doc.add_paragraph()
    par.paragraph_format.space_after = Pt(space_after)
    run = par.add_run(text)
    run.bold, run.italic = bold, italic
    if size: run.font.size = Pt(size)
    return par

def table(headers, rows, widths=None, font=9.5):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(headers):
        c = t.rows[0].cells[j]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(font)
    for row in rows:
        cells = t.add_row().cells
        for j, v in enumerate(row):
            cells[j].text = ""
            r = cells[j].paragraphs[0].add_run(str(v))
            r.font.size = Pt(font)
    if widths:
        for j, w in enumerate(widths):
            for row in t.rows:
                row.cells[j].width = Inches(w)
    return t

# ---------------- Title ----------------
tp = doc.add_paragraph(); tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = tp.add_run("Software Engineering Practices — Part 1 (Tasks 4–7)")
r.bold = True; r.font.size = Pt(18); r.font.color.rgb = RGBColor.from_string("1F5AA8")
tp2 = doc.add_paragraph(); tp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = tp2.add_run("Project: Library Seat Management System (Real-time AI-based Library Seat Monitoring Platform)")
r.bold = True; r.font.size = Pt(12)
p("Contributors: Chenhao Guan, Yixuan Lu, Hongtian Chen", italic=True, size=9.5)

# ================= TASK 4 =================
doc.add_heading("Task 4: Functional and Non-Functional Requirements", level=1)

doc.add_heading("4.1 Functional Requirements", level=2)
p("The functional requirements were derived from the customer's problem (students waste "
  "time searching for free library seats; staff cannot detect seat-hogging behaviour), the "
  "agreed project scope, and the implemented system. They are grouped into seven areas.")
table(
    ["ID", "Requirement", "Description", "Module"],
    [
        ["FR-01", "User registration", "New users can create an account with username and password (password stored as a bcrypt hash); every new account receives the default role “student”.", "Auth"],
        ["FR-02", "Login / Logout", "Registered users log in with username and password and receive a JWT (default validity 120 min); logout invalidates the session client-side and, when the last user logs out, stops the detection scheduler.", "Auth"],
        ["FR-03", "Floor overview", "The system lists all floors with the number of empty / total seats and a floor colour (green > 50% empty, yellow 0–50%, red 0% empty).", "Seat & Floor"],
        ["FR-04", "Real-time seat map", "For each floor the system displays a seat map where every seat is colour-coded: green = free (no socket), blue = free (with power socket), grey = occupied, yellow = reported by a user.", "Seat & Floor"],
        ["FR-05", "Seat details & statistics", "Clicking a seat shows its ID, floor, power availability and status; the backend additionally exposes per-seat statistics (empty seconds today/total, state-change count, object-only occupancy duration).", "Seat & Floor"],
        ["FR-06", "Seat reporting", "Any logged-in user can report a seat problem (e.g., seat hogging) with an optional text description and photo evidence (camera or gallery, JPG/JPEG/PNG only, ≤ 5 MB per image). A reported seat turns yellow.", "Reporting"],
        ["FR-07", "Report storage", "Reports (text + image paths) are persisted; images are stored on the server and served statically for later inspection.", "Reporting"],
        ["FR-08", "Anomaly list", "Administrators see a list of all anomalous seats (user-reported and system-flagged), with floor filter and keyword search.", "Admin"],
        ["FR-09", "Report inspection", "Administrators open a report’s details, including text and photo evidence.", "Admin"],
        ["FR-10", "Confirm / dismiss anomaly", "Administrators confirm an anomaly (seat marked “malicious”, shown to admins with inverted colour) or dismiss it, which clears the malicious mark.", "Admin"],
        ["FR-11", "Clear anomaly", "Administrators can clear a seat’s anomaly state; pending reports for that seat are automatically dismissed.", "Admin"],
        ["FR-12", "Seat locking", "Administrators can lock a seat for 5 minutes so that automatic detection does not overwrite its visual state while the case is being handled.", "Admin"],
        ["FR-13", "Manual floor refresh", "Administrators can trigger an immediate YOLO re-detection of a floor instead of waiting for the next scheduled cycle.", "Admin"],
        ["FR-14", "Automatic occupancy detection", "For every configured floor the system periodically (default every 8 s, configurable) samples ~1 s of the camera stream, runs YOLOv11 object detection, maps persons/objects to seat regions (ROI polygons) and updates each seat’s empty/occupied state (presence threshold ≥ 30% of frames).", "AI Detection"],
        ["FR-15", "Malicious-occupancy auto-alarm", "If a seat region contains only objects (bag, book, laptop …) and no person for more than 2 hours, the system automatically flags the seat as “malicious” and raises a system alarm that appears in the admin anomaly list.", "AI Detection"],
        ["FR-16", "Daily statistics export", "At 00:00 every day the system exports per-seat / per-floor / library empty-time statistics for the previous day to outputs/YYYY-MM-DD/daily_empty.txt and resets daily counters and all anomaly flags.", "Data & Stats"],
        ["FR-17", "Monthly statistics export", "On the first day of each month the previous month’s total empty-time statistics are exported to outputs/monthly/YYYY-MM.txt and monthly counters are reset; missed exports are caught up after downtime.", "Data & Stats"],
        ["FR-18", "Multi-language UI", "The user interface can be switched between English, Simplified Chinese and Traditional Chinese.", "UI"],
        ["FR-19", "Responsive cross-platform UI", "The Flutter client adapts its layout to mobile and desktop screens and runs on Android, iOS, Web, Windows, macOS and Linux.", "UI"],
    ],
    widths=[0.55, 1.45, 4.05, 0.95],
)
p("")

doc.add_heading("4.2 Non-Functional Requirements", level=2)
table(
    ["ID", "Category", "Requirement / Target"],
    [
        ["NFR-01", "Performance", "Seat status is refreshed automatically every 8 s (configurable via REFRESH_INTERVAL_SECONDS); the app polls every 2 s so users see changes within seconds; YOLO inference uses GPU (CUDA, FP16) when available, otherwise CPU."],
        ["NFR-02", "Security", "Passwords are bcrypt-hashed; all APIs except login/registration require a signed JWT (HS256); admin endpoints enforce role-based access control (403 for non-admins); uploaded images are validated server-side (extension whitelist jpg/jpeg/png)."],
        ["NFR-03", "Robustness / Reliability", "Malformed floor/ROI configuration is rejected by a strict validator; the config loader survived a 4-hour, 268-million-execution fuzzing campaign with zero crashes; if a refresh fails (e.g., missing video), the API gracefully falls back to the last stored database state."],
        ["NFR-04", "Availability & efficiency", "The YOLO scheduler starts on demand when the first user logs in and shuts down when the last user logs out, saving GPU/CPU resources when nobody uses the app."],
        ["NFR-05", "Usability", "Intuitive traffic-light colour coding for seats and floors; multilingual UI; silent background refresh without loading flickers; one-tap photo evidence upload."],
        ["NFR-06", "Scalability", "Floors are configuration-driven (JSON ROI files): new floors/seats are added without code changes; per-floor locks allow parallel multi-camera processing; the detector is a shared singleton."],
        ["NFR-07", "Portability", "Backend: Python/FastAPI with zero-configuration SQLite; frontend: single Flutter code base for six platforms; startup scripts automate environment setup."],
        ["NFR-08", "Maintainability", "Clear layering (routes / services / scheduler / models), automatic OpenAPI documentation (Swagger UI at /docs), environment-variable configuration, README-driven setup."],
        ["NFR-09", "Data integrity", "Daily and monthly rollover jobs export and reset statistics atomically; an offline catch-up routine re-runs missed exports after server downtime."],
        ["NFR-10", "Privacy", "Only seat occupancy is derived from video — no personal identification or face recognition is performed or stored; report photos are stored per-report in a non-guessable folder structure."],
    ],
    widths=[0.6, 1.35, 6.05],
)

# ================= TASK 5 =================
doc.add_heading("Task 5: Use-Case Diagram and Detailed Description", level=1)

doc.add_heading("5.1 Actors", level=2)
table(
    ["Actor", "Type", "Description"],
    [
        ["Student (Library User)", "Primary", "A library visitor who wants to quickly find a free seat and can help keep the data honest by reporting seat-hogging."],
        ["Administrator (Library Staff)", "Primary", "Library employee who monitors anomalies, verifies user reports and manages the detection system."],
        ["Camera / Video Stream", "Secondary (external)", "One surveillance camera per floor providing the video frames that the YOLO engine analyses."],
        ["System Scheduler (Timer)", "Secondary (internal)", "Time-based trigger that starts the periodic detection cycle, the auto-alarm check and the daily/monthly statistics exports."],
    ],
    widths=[1.6, 1.3, 5.1],
)
p("")

doc.add_heading("5.2 Use-Case Diagram", level=2)
doc.add_picture(PNG, width=Inches(6.9))
p("Figure 1 — Use-case diagram of the Library Seat Management System", italic=True, size=9)

doc.add_heading("5.3 Use-Case Overview", level=2)
table(
    ["ID", "Use Case", "Actor(s)", "Brief Description"],
    [
        ["UC1", "Register Account", "Student", "Create a new student account."],
        ["UC2", "Log In / Log Out", "Student, Admin", "Authenticate and receive a JWT; log out ends the session."],
        ["UC3", "View Floor Map & Seat Status", "Student, Admin", "Browse the colour-coded floor overview and seat map."],
        ["UC4", "View Seat Details / Statistics", "Student, Admin", "Open per-seat information (power, status, statistics)."],
        ["UC5", "Report Seat Issue", "Student, Admin", "Report a seat problem with text and photo evidence."],
        ["UC6", "Upload Photo Evidence", "Student, Admin (included in UC5)", "Attach camera/gallery photos (JPG/PNG, ≤ 5 MB) to a report."],
        ["UC7", "Switch Language", "Student, Admin", "Change UI language (EN / 简体中文 / 繁體中文)."],
        ["UC8", "View Anomaly List", "Admin", "See all reported / system-flagged seats with filter and search."],
        ["UC9", "View Report Details & Images", "Admin (included in UC8)", "Inspect the text and photos of a specific report."],
        ["UC10", "Confirm / Dismiss Anomaly", "Admin (extends UC8)", "Mark a seat as malicious or dismiss the report."],
        ["UC11", "Clear Anomaly", "Admin (extends UC8)", "Reset a seat’s anomaly state and dismiss pending reports."],
        ["UC12", "Lock Seat", "Admin (extends UC8)", "Freeze a seat’s visual state for 5 minutes while handling the case."],
        ["UC13", "Trigger Floor Refresh", "Admin", "Force an immediate YOLO re-detection of one floor."],
        ["UC14", "Detect Seat Occupancy", "Camera, Scheduler", "Periodic YOLOv11 analysis of the video stream mapped to seat ROIs."],
        ["UC15", "Raise System Auto-Alarm", "Scheduler (extends UC14)", "Flag seats occupied only by objects for > 2 h as malicious."],
        ["UC16", "Export Daily/Monthly Statistics", "Scheduler", "Export and reset empty-time statistics."],
    ],
    widths=[0.45, 1.7, 1.6, 4.25],
)
p("")

doc.add_heading("5.4 Detailed Use-Case Descriptions", level=2)

def uc_table(title, fields):
    doc.add_heading(title, level=3)
    t = doc.add_table(rows=0, cols=2); t.style = "Table Grid"
    for k, v in fields:
        row = t.add_row().cells
        row[0].text = ""; row[1].text = ""
        r1 = row[0].paragraphs[0].add_run(k); r1.bold = True; r1.font.size = Pt(9.5)
        r2 = row[1].paragraphs[0].add_run(v); r2.font.size = Pt(9.5)
        row[0].width = Inches(1.35); row[1].width = Inches(5.65)
    p("")

uc_table("UC2 — Log In", [
    ("Actor", "Student / Administrator"),
    ("Precondition", "The user has a registered account; the backend server is running."),
    ("Main flow", "1. User opens the app. 2. User enters username and password. 3. System validates the credentials against the bcrypt-hashed record. 4. System issues a JWT (valid 120 min) and stores it locally. 5. System starts the YOLO detection scheduler if it is not already running. 6. User is routed to the floor map (student) or can open the admin page (admin)."),
    ("Alternative flows", "3a. Wrong credentials → 401 error, message shown, retry allowed. 3b. Username contains non-alphanumeric characters or password < 6 chars → client-side validation error."),
    ("Postcondition", "User is authenticated; scheduler is running; last-login role determines the visible features."),
])

uc_table("UC3 — View Floor Map & Seat Status", [
    ("Actor", "Student / Administrator"),
    ("Precondition", "User is logged in (UC2)."),
    ("Main flow", "1. System loads the floor list (empty/total counts + floor colour). 2. User selects a floor. 3. System fetches all seats of that floor and renders the seat map. 4. A background timer silently re-fetches data every 2 s so the map reflects the 8 s detection cycle without a loading spinner."),
    ("Alternative flows", "4a. Backend unreachable → the client falls back to the last cached/hard-coded layout and continues retrying silently."),
    ("Postcondition", "The user sees the current occupancy of every seat, colour-coded (green/blue = free, grey = occupied, yellow = reported)."),
])

uc_table("UC5 — Report Seat Issue", [
    ("Actor", "Student (any logged-in user, incl. admin)"),
    ("Precondition", "User is logged in and has selected a seat."),
    ("Main flow", "1. User taps a seat and chooses “Report”. 2. User optionally types a description. 3. User adds photo evidence from camera or gallery (include UC6). 4. Client validates file type (JPG/JPEG/PNG) and size (≤ 5 MB). 5. Report is uploaded as multipart form data. 6. Server re-validates, stores text and images, and marks the seat as reported. 7. Seat turns yellow for all users; report status = pending."),
    ("Alternative flows", "4a/5a. Invalid type or size → upload rejected with a clear message. 6a. Unknown seat id → 400 error. 6b. Image saving fails → transaction rolled back, 500 returned."),
    ("Postcondition", "The report is stored and appears in the admin anomaly list; the seat is visually flagged until an admin acts on it or the daily reset clears it."),
])

uc_table("UC8/UC10 — Manage Anomalies (View List / Confirm / Dismiss)", [
    ("Actor", "Administrator"),
    ("Precondition", "Admin is logged in with role = admin (non-admins receive 403)."),
    ("Main flow", "1. Admin opens the Anomaly Management page. 2. System lists all seats with is_reported or is_malicious flags, with floor filter and search. 3. Admin opens a report to inspect text and photos (include UC9). 4. Admin confirms the anomaly → the seat is marked malicious, the report becomes “confirmed”, the seat is locked for 5 minutes (include UC12) and is displayed to admins with inverted colour. 5. Admin may instead dismiss the anomaly (malicious flag cleared, report “dismissed”) or fully clear the seat (all flags reset, pending reports dismissed)."),
    ("Alternative flows", "2a. Backend timeout (15 s) → mock/demo data is shown and the user is informed. 4a. API error → local state is rolled back and an error snackbar is shown."),
    ("Postcondition", "The anomaly list reflects the admin’s decision; confirmed seat-hogging cases stay highlighted for staff action."),
])

uc_table("UC14 — Detect Seat Occupancy (automatic)", [
    ("Actor", "Camera / Video Stream (external), System Scheduler (timer trigger)"),
    ("Precondition", "At least one user is logged in (scheduler running); a valid floor configuration (JSON with seat ROI polygons and stream path) exists."),
    ("Main flow", "1. Every 8 s the scheduler triggers a refresh per floor. 2. The system samples ~1 s of frames from the floor’s camera stream. 3. YOLOv11 detects persons and 12 object classes (backpack, laptop, book, …). 4. Detections are mapped to seat ROI polygons (ray-casting point-in-polygon). 5. A seat counts as occupied if persons or objects appear in ≥ 30% of sampled frames. 6. Empty-time statistics are accumulated; seat states are updated in the database (unless the seat is admin-locked)."),
    ("Alternative flows", "2a. Stream missing/unreadable → previous database state is kept. 4a. New seat ids found in config are auto-created in the database. 6a. Day/month changed since last run → missed daily/monthly exports are executed first."),
    ("Postcondition", "Seat states and statistics in the database match the latest camera observations and are served to all clients."),
])

uc_table("UC15 — Raise System Auto-Alarm (automatic)", [
    ("Actor", "System Scheduler (extends UC14)"),
    ("Precondition", "Detection is running for the floor."),
    ("Main flow", "1. During each refresh the system tracks per seat how long only objects (no person) have been detected in the seat region. 2. When this object-only occupancy exceeds 2 hours, the seat is automatically flagged as malicious. 3. The flagged seat appears in the admin anomaly list (system-reported) and is shown to admins with inverted colour."),
    ("Alternative flows", "1a. A person is detected again → the occupancy timer resets and no alarm is raised."),
    ("Postcondition", "Long-term seat-hogging (占座) is detected without any human report and escalated to staff."),
])

# ================= TASK 6 =================
doc.add_heading("Task 6: Methods Used to Analyze the Requirements", level=1)
p("We combined classic elicitation techniques with object-oriented analysis and iterative "
  "prototyping. For each method we describe how it was applied and what it contributed to "
  "the final requirement list.")

doc.add_heading("6.1 Stakeholder Analysis", level=2)
p("We first identified all stakeholders — students (primary users), library administrators/staff "
  "(secondary users), the university library department (customer), and our development team. "
  "Analysing their goals (“find a seat fast”, “keep order”, “get usage statistics”) kept the "
  "scope focused and produced the two-actor model that later drove the use-case diagram.")

doc.add_heading("6.2 Interviews and Questionnaires (survey analysis)", level=2)
p("Short interviews with library staff revealed the pain point of manual patrol and the need for "
  "evidence-based handling of seat-hogging. A questionnaire among students quantified how much "
  "time is wasted searching for seats and which features matter most (real-time availability, "
  "power-socket filter). The quantitative answers were ranked and translated into prioritised "
  "functional requirements (e.g., FR-03/FR-04 real-time map, FR-05 power information).")

doc.add_heading("6.3 Field Observation", level=2)
p("We observed the library reading room at peak hours and reviewed the surveillance camera "
  "perspective. This confirmed the key behavioural pattern behind the whole project: students "
  "leave bags/books on seats for hours (object-only occupancy), which only a camera-based "
  "system can detect. Observation directly produced FR-15 (2-hour malicious-occupancy rule, "
  "30% frame-presence thresholds).")

doc.add_heading("6.4 Document & Domain Analysis", level=2)
p("We studied the library’s opening hours and seat rules, existing seat-booking apps, and "
  "object-detection literature (YOLO series, COCO classes). This grounded technical choices "
  "(YOLOv11 + per-seat ROI polygons instead of face-based approaches, also for privacy reasons — NFR-10) "
  "and identified statistics requirements (FR-16/FR-17).")

doc.add_heading("6.5 Use-Case Modelling and Scenario Analysis (Object-Oriented Analysis)", level=2)
p("Requirements were structured with UML use-case modelling: actors, system boundary, "
  "«include»/«extend» relationships (Task 5). Concrete scenarios were walked through "
  "(“a student reports a bag on a seat”, “an admin confirms it”, “the system auto-alarms after 2 h”) "
  "to discover missed flows, preconditions and alternative flows — e.g., the 5-minute seat lock "
  "(FR-12) emerged from the scenario “admin is handling a seat while detection overwrites its colour”.")

doc.add_heading("6.6 Prototyping (Evolutionary / Throw-away MVP)", level=2)
p("An early clickable UI prototype and a walking-skeleton demo (one camera, four seats) were shown "
  "to stakeholders. Feedback such as “colours must also be understandable at floor level” led to the "
  "floor colour rules (FR-03) and the three-language requirement (FR-18). Prototyping also validated "
  "the 8-second refresh as a “real-time enough” compromise between accuracy and GPU load.")

doc.add_heading("6.7 Brainstorming and Prioritisation (MoSCoW)", level=2)
p("Team brainstorming sessions generated the full feature wish-list (e.g., seat reservation, "
  "notification push, heat maps). We prioritised it with MoSCoW: Must-have (real-time seat map, "
  "reporting, admin handling, occupancy detection), Should-have (auto-alarm, statistics export, "
  "multi-language), Could-have (mock floors for demo, seat locking), Won’t-have-this-time "
  "(reservation system, push notifications) to keep the MVP achievable within one semester.")

# ================= TASK 7 =================
doc.add_heading("Task 7: Technologies Used to Collect and Analyze Requirements", level=1)
p("Task 7 focuses on the tools and technologies that supported the elicitation and analysis "
  "activities described in Task 6.")

doc.add_heading("7.1 Technologies for Collecting Requirements", level=2)
table(
    ["Technology / Tool", "How it was used"],
    [
        ["Face-to-face interviews & meeting notes", "Semi-structured interviews with library staff and students; findings captured as shared meeting minutes."],
        ["Online questionnaire (WeChat / Wenjuan forms)", "Distributed to students to quantify seat-searching time and feature priorities; exported results analysed statistically."],
        ["Field observation & video review", "Direct observation of the reading room and inspection of surveillance footage to identify the object-only occupancy pattern."],
        ["Document analysis", "Library rules, opening hours, existing apps and YOLO/COCO literature as sources for domain constraints and technical feasibility."],
        ["Low-fidelity prototypes (Flutter MVP)", "Clickable early UI demonstrated to stakeholders to collect concrete, visual feedback instead of abstract opinions."],
        ["Brainstorming sessions (whiteboard + shared docs)", "Team-internal idea generation followed by MoSCoW prioritisation in a shared document."],
    ],
    widths=[2.4, 5.6],
)
p("")

doc.add_heading("7.2 Technologies for Analyzing Requirements", level=2)
table(
    ["Technology / Tool", "How it was used"],
    [
        ["UML use-case modelling", "Actor/system-boundary/use-case model with «include» and «extend» relationships (Figure 1); the basis for requirement traceability from user goals to functions."],
        ["Scenario / walkthrough analysis", "Step-by-step walkthroughs of key scenarios to derive main and alternative flows, pre- and postconditions."],
        ["Requirements tables & traceability lists", "Functional (FR-xx) and non-functional (NFR-xx) requirements maintained as numbered tables, each traceable to a source (interview, survey, observation) and to a system module."],
        ["Statistical analysis of survey data", "Ranking and simple quantitative analysis of questionnaire answers to prioritise features."],
        ["Proof-of-technology experiments", "Early YOLO detection trials on sample camera footage to validate that the 30%/2-hour thresholds are technically measurable, turning a business rule into a verifiable requirement."],
        ["Fuzzing & robustness testing (Atheris)", "A 268-million-execution fuzzing campaign of the configuration loader verified that the validated configuration format (a core requirement input) is robust — evidence supporting NFR-03."],
    ],
    widths=[2.4, 5.6],
)
p("")

doc.add_heading("7.3 Summary", level=2)
p("The combination of stakeholder analysis, interviews, questionnaires, observation, domain "
  "analysis, UML use-case modelling, prototyping and MoSCoW prioritisation ensured that the "
  "final requirements are complete, prioritised, verifiable and traceable: every FR/NFR in Task 4 "
  "maps back to at least one elicitation source and forward to a concrete system module, and the "
  "use-case model in Task 5 is directly derived from the same analysis.")

doc.save(os.path.join(BASE, "Task4-7_Requirements_Analysis.docx"))
print("DOCX saved")
