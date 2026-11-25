"""
Web dashboard: upload students (ID + name + photo), view daily period-wise attendance,
and see attendance percentages.

Install once:  python -m pip install flask
Run:           python dashboard.py
Open:          http://127.0.0.1:5000
   /          daily attendance (8 periods)
   /summary   attendance % per student
   /students  add students and upload their photos
"""

import glob
import os
import re
import shutil
import tempfile
from datetime import date

import numpy as np
from flask import Flask, redirect, render_template_string, request, send_from_directory, url_for

from config import (DEFAULTER_THRESHOLD, DUPLICATE_TOLERANCE, PERIODS_PER_DAY,
                    TOTAL_WORKING_DAYS, is_working_day)
from database import (BASE_DIR, attendance_summary, get_all_students, get_conn, get_student,
                      load_encodings, save_encodings)
import face_utils

PHOTO_DIR = os.path.join(BASE_DIR, "student_photos")
os.makedirs(PHOTO_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024

BASE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Attendance</title>
%%REFRESH%%
<style>
  body{font-family:Segoe UI,Arial,sans-serif;background:#f4f6f8;margin:0;color:#222}
  header{background:#0f766e;color:#fff;padding:16px 28px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
  header h1{font-size:20px;margin:0;flex:1}
  header a{color:#fff;text-decoration:none;font-weight:600;padding:6px 12px;border-radius:6px}
  header a.active{background:rgba(255,255,255,.22)}
  main{max-width:1100px;margin:24px auto;padding:0 16px}
  .cards{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:20px}
  .card{flex:1;min-width:150px;background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  .card b{display:block;font-size:26px}
  table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #eee;font-size:14px}
  th{background:#e7eef0}
  .tag{padding:3px 9px;border-radius:12px;font-weight:600;font-size:12px;display:inline-block;min-width:16px;text-align:center}
  .Present{background:#d1fae5;color:#065f46}
  .Absent{background:#fee2e2;color:#991b1b}
  .Notrecorded{background:#fef3c7;color:#92400e}
  .None{background:#f3f4f6;color:#9ca3af}
  .bar{background:#e5e7eb;border-radius:6px;height:12px;width:120px;display:inline-block;vertical-align:middle}
  .bar span{display:block;height:100%;border-radius:6px}
  .box{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:22px}
  .box label{display:block;margin:10px 0 4px;font-weight:600;font-size:13px}
  .box input{padding:8px;font-size:14px;width:100%;max-width:380px;box-sizing:border-box}
  button{padding:9px 18px;font-size:14px;background:#0f766e;color:#fff;border:0;border-radius:6px;cursor:pointer;margin-top:14px}
  .notice{padding:12px 16px;border-radius:8px;margin-bottom:16px;background:#e0f2fe;color:#075985}
  .notice.ok{background:#d1fae5;color:#065f46}
  .notice.err{background:#fee2e2;color:#991b1b}
  .low td{background:#fff7f7}
  .hint{color:#666;font-size:13px;margin-top:8px}
  img.face{width:44px;height:44px;object-fit:cover;border-radius:50%}
</style>
</head>
<body>
<header>
  <h1>Smart Attendance System</h1>
  <a href="/" class="%%A1%%">Daily</a>
  <a href="/summary" class="%%A2%%">Summary</a>
  <a href="/students" class="%%A3%%">Students</a>
</header>
<main>%%CONTENT%%</main>
</body></html>
"""

DAILY = """
<form method="get">
  <label>Date: <input type="date" name="date" value="{{ day }}" style="padding:7px"></label>
  <button style="margin:0 0 0 8px">View</button>
</form><br>
{% if weekend %}<div class="notice">{{ weekday }} - weekend. No classes and no attendance.</div>{% endif %}
<div class="cards">
  <div class="card"><b>{{ taken|length }} / {{ nperiods }}</b>Periods taken</div>
  <div class="card"><b>{{ present_marks }}</b>Present marks</div>
  <div class="card"><b>{{ absent_marks }}</b>Absent marks</div>
  <div class="card"><b>{{ rows|length }}</b>Students</div>
</div>
<table>
  <tr><th>ID</th><th>Name</th><th>Class</th>
      {% for p in periods %}<th>P{{ p }}</th>{% endfor %}<th>Day</th></tr>
  {% for r in rows %}
  <tr>
    <td>{{ r.student_id }}</td><td>{{ r.name }}</td><td>{{ r.class_name or '' }}</td>
    {% for p in periods %}{% set c = r.cells[p] %}
      <td><span class="tag {{ c.cls }}" title="{{ c.tip }}">{{ c.label }}</span></td>
    {% endfor %}
    <td><b>{{ r.day_present }}/{{ taken|length }}</b></td>
  </tr>
  {% else %}<tr><td colspan="12">No students yet. Add them on the Students page.</td></tr>{% endfor %}
</table>
<p class="hint">P = present, A = absent, – = period not taken. Hover a cell for the time or reason.</p>
"""

SUMMARY = """
<div class="cards">
  <div class="card"><b>{{ meta.days_held }} / {{ total_days }}</b>Working days held</div>
  <div class="card"><b>{{ meta.days_remaining }}</b>Working days remaining</div>
  <div class="card"><b>{{ meta.periods_held }} / {{ meta.total_year_periods }}</b>Periods held</div>
  <div class="card"><b>{{ defaulters }}</b>Below {{ threshold|int }}% so far</div>
</div>
<table>
  <tr><th>ID</th><th>Name</th><th>Class</th><th>Present</th><th>Absent</th><th>Held</th>
      <th>% so far</th><th>% of {{ total_days }} days</th></tr>
  {% for r in rows %}
  <tr class="{{ 'low' if meta.periods_held and r.pct_so_far < threshold else '' }}">
    <td>{{ r.student_id }}</td><td>{{ r.name }}</td><td>{{ r.class_name or '' }}</td>
    <td>{{ r.present }}</td><td>{{ r.absent }}</td><td>{{ r.held }}</td>
    <td><span class="bar"><span style="width:{{ r.pct_so_far }}%;background:{{ '#dc2626' if r.pct_so_far < threshold else '#0f766e' }}"></span></span>
        &nbsp;<b>{{ r.pct_so_far }}%</b></td>
    <td><b>{{ r.pct_year }}%</b></td>
  </tr>
  {% else %}<tr><td colspan="8">No students yet.</td></tr>{% endfor %}
</table>
<p class="hint">
  <b>% so far</b> = periods present &divide; periods held until now (used for the {{ threshold|int }}% defaulter check).<br>
  <b>% of {{ total_days }} days</b> = periods present &divide; ({{ total_days }} working days &times; {{ nperiods }} periods = {{ meta.total_year_periods }}).
  Saturdays and Sundays are never counted.
</p>
"""

STUDENTS = """
{% if msg %}<div class="notice {{ 'ok' if ok == '1' else 'err' }}">{{ msg }}</div>{% endif %}
<div class="box">
  <h3 style="margin-top:0">Add or update a student</h3>
  <form method="post" action="/students/save" enctype="multipart/form-data">
    <label>Student ID *</label><input name="student_id" required placeholder="e.g. 101" pattern="[A-Za-z0-9\\-]{1,20}">
    <label>Name *</label><input name="name" required placeholder="Full name">
    <label>Class</label><input name="class_name" placeholder="e.g. 10-A">
    <label>Parent email</label><input name="parent_email" type="email" placeholder="parent@example.com">
    <label>Face photo(s) * (JPG/PNG, 1 to 5 photos)</label>
    <input name="photos" type="file" accept="image/png,image/jpeg" multiple>
    <div class="hint">Use clear, front-facing photos of ONLY this student, with good light. Each photo is checked
      for exactly one face. Submit an existing ID again to update details or replace the photos.</div>
    <button>Save student</button>
  </form>
</div>
<table>
  <tr><th>Photo</th><th>ID</th><th>Name</th><th>Class</th><th>Parent email</th><th>Face data</th></tr>
  {% for s in students %}
  <tr>
    <td>{% if s.photo_path %}<img class="face" src="/photos/{{ s.photo_path }}">{% endif %}</td>
    <td>{{ s.student_id }}</td><td>{{ s.name }}</td><td>{{ s.class_name or '' }}</td>
    <td>{{ s.parent_email or '' }}</td>
    <td>{% if counts.get(s.student_id) %}<span class="tag Present">{{ counts[s.student_id] }} photo(s) ready</span>
        {% else %}<span class="tag Absent">no photo</span>{% endif %}</td>
  </tr>
  {% else %}<tr><td colspan="6">No students yet.</td></tr>{% endfor %}
</table>
"""


def page(content, active, refresh=False, **ctx):
    html = BASE.replace("%%CONTENT%%", content)
    html = html.replace("%%REFRESH%%", '<meta http-equiv="refresh" content="15">' if refresh else "")
    for i in (1, 2, 3):
        html = html.replace(f"%%A{i}%%", "active" if active == i else "")
    return render_template_string(html, **ctx)


@app.route("/")
def daily():
    try:
        d = date.fromisoformat(request.args.get("date", ""))
    except ValueError:
        d = date.today()
    day = d.isoformat()

    conn = get_conn()
    students = [dict(s) for s in get_all_students(conn)]
    taken = {r["period"] for r in conn.execute("SELECT period FROM sessions WHERE date=?", (day,))}
    att = {(r["student_id"], r["period"]): r for r in conn.execute(
        "SELECT student_id, period, status, time, reason FROM attendance WHERE date=?", (day,))}
    conn.close()

    present_marks = absent_marks = 0
    for s in students:
        s["cells"], s["day_present"] = {}, 0
        for p in range(1, PERIODS_PER_DAY + 1):
            if p not in taken:
                s["cells"][p] = {"label": "–", "cls": "None", "tip": "Period not taken"}
                continue
            rec = att.get((s["student_id"], p))
            if rec is None:
                s["cells"][p] = {"label": "?", "cls": "Notrecorded", "tip": "Not recorded"}
            elif rec["status"] == "Present":
                s["cells"][p] = {"label": "P", "cls": "Present", "tip": f"Present at {rec['time']}"}
                s["day_present"] += 1
                present_marks += 1
            else:
                s["cells"][p] = {"label": "A", "cls": "Absent",
                                 "tip": f"Absent - {rec['reason'] or ''}"}
                absent_marks += 1

    return page(DAILY, 1, refresh=(day == date.today().isoformat()), day=day, rows=students,
                periods=range(1, PERIODS_PER_DAY + 1), nperiods=PERIODS_PER_DAY, taken=taken,
                weekend=not is_working_day(d), weekday=d.strftime("%A"),
                present_marks=present_marks, absent_marks=absent_marks)


@app.route("/summary")
def summary():
    conn = get_conn()
    rows, meta = attendance_summary(conn)
    conn.close()
    defaulters = sum(1 for r in rows if meta["periods_held"] and r["pct_so_far"] < DEFAULTER_THRESHOLD)
    return page(SUMMARY, 2, rows=rows, meta=meta, threshold=DEFAULTER_THRESHOLD,
                total_days=TOTAL_WORKING_DAYS, nperiods=PERIODS_PER_DAY, defaulters=defaulters)


@app.route("/students")
def students():
    conn = get_conn()
    rows = [dict(s) for s in get_all_students(conn)]
    counts = {r["student_id"]: r["n"] for r in conn.execute(
        "SELECT student_id, COUNT(*) AS n FROM face_encodings GROUP BY student_id")}
    conn.close()
    return page(STUDENTS, 3, students=rows, counts=counts,
                msg=request.args.get("msg"), ok=request.args.get("ok", "0"))


@app.route("/photos/<path:filename>")
def photos(filename):
    return send_from_directory(PHOTO_DIR, filename)


def _back(msg, ok):
    return redirect(url_for("students", msg=msg, ok="1" if ok else "0"))


@app.route("/students/save", methods=["POST"])
def save_student():
    sid = request.form.get("student_id", "").strip()
    name = request.form.get("name", "").strip()
    class_name = request.form.get("class_name", "").strip()
    parent_email = request.form.get("parent_email", "").strip()
    files = [f for f in request.files.getlist("photos") if f and f.filename]

    if not re.fullmatch(r"[A-Za-z0-9\-]{1,20}", sid):
        return _back("Student ID may only contain letters, numbers and '-' (max 20 characters).", False)
    if not name:
        return _back("Name is required.", False)
    if len(files) > 5:
        return _back("Upload at most 5 photos.", False)

    conn = get_conn()
    exists = get_student(conn, sid) is not None
    if not files and not exists:
        conn.close()
        return _back("Upload at least one clear face photo for a new student.", False)

    tmp = tempfile.mkdtemp()
    try:
        encodings, tmp_paths = [], []
        for i, f in enumerate(files, 1):
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png"):
                return _back(f"{f.filename}: only JPG or PNG images are allowed.", False)
            path = os.path.join(tmp, f"{sid}_{i}{ext}")
            f.save(path)

            enc, err = face_utils.get_single_face_encoding(path)
            if err:
                return _back(f"{f.filename}: {err}", False)

            known, known_ids = load_encodings(conn, exclude_id=sid)
            if len(known):
                dists = np.linalg.norm(known - enc, axis=1)
                j = int(np.argmin(dists))
                if dists[j] <= DUPLICATE_TOLERANCE:
                    other = get_student(conn, known_ids[j])
                    who = f"{other['name']} ({other['student_id']})" if other else known_ids[j]
                    return _back(f"{f.filename}: this face is already registered for {who}.", False)

            encodings.append(enc)
            tmp_paths.append(path)

        first_photo = None
        if encodings:
            for old in glob.glob(os.path.join(PHOTO_DIR, f"{sid}_*")):
                os.remove(old)
            for p in tmp_paths:
                shutil.move(p, os.path.join(PHOTO_DIR, os.path.basename(p)))
            first_photo = os.path.basename(tmp_paths[0])
            save_encodings(conn, sid, encodings)

        conn.execute(
            """INSERT INTO students (student_id, name, class_name, parent_email, photo_path)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(student_id) DO UPDATE SET
                   name=excluded.name, class_name=excluded.class_name,
                   parent_email=excluded.parent_email,
                   photo_path=COALESCE(excluded.photo_path, students.photo_path)""",
            (sid, name, class_name, parent_email, first_photo))
        conn.commit()
    finally:
        conn.close()
        shutil.rmtree(tmp, ignore_errors=True)

    action = "updated" if exists else "added"
    extra = f" with {len(encodings)} face photo(s)" if encodings else ""
    return _back(f"{name} ({sid}) {action}{extra}.", True)


if __name__ == "__main__":
    print("Open http://127.0.0.1:5000 in your browser (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=5000, debug=False)
