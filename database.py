"""
Shared database layer (SQLite: attendance.db, stored next to these scripts).

students       roster (id, name, class, parent email, photo file name)
face_encodings 128-d face encodings made from the uploaded student photos
sessions       every (date, period) for which attendance was taken
attendance     one row per student per date per period: Present / Absent
"""

import os
import sqlite3
from datetime import datetime

import numpy as np

from config import PERIODS_PER_DAY, TOTAL_WORKING_DAYS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "attendance.db")


def _columns(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # Upgrade databases made by the older (one-record-per-day) version
    old = _columns(conn, "attendance")
    if old and "period" not in old:
        conn.execute("ALTER TABLE attendance RENAME TO attendance_old")

    conn.execute("""CREATE TABLE IF NOT EXISTS students (
                        student_id   TEXT PRIMARY KEY,
                        name         TEXT NOT NULL,
                        class_name   TEXT,
                        parent_email TEXT,
                        photo_path   TEXT
                    )""")
    if "photo_path" not in _columns(conn, "students"):
        conn.execute("ALTER TABLE students ADD COLUMN photo_path TEXT")

    conn.execute("""CREATE TABLE IF NOT EXISTS face_encodings (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id TEXT NOT NULL,
                        encoding   BLOB NOT NULL
                    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
                        date       TEXT NOT NULL,
                        period     INTEGER NOT NULL,
                        started_at TEXT,
                        PRIMARY KEY (date, period)
                    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS attendance (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id TEXT NOT NULL,
                        date       TEXT NOT NULL,
                        period     INTEGER NOT NULL,
                        time       TEXT,
                        status     TEXT NOT NULL CHECK (status IN ('Present', 'Absent')),
                        reason     TEXT,
                        UNIQUE (student_id, date, period)
                    )""")
    conn.commit()
    return conn


# ---------- students & faces ----------
def get_student(conn, student_id):
    return conn.execute("SELECT * FROM students WHERE student_id=?", (student_id,)).fetchone()


def get_all_students(conn):
    return conn.execute("SELECT * FROM students ORDER BY student_id").fetchall()


def save_encodings(conn, student_id, encodings):
    """Replace all stored face encodings of a student."""
    conn.execute("DELETE FROM face_encodings WHERE student_id=?", (student_id,))
    for enc in encodings:
        conn.execute("INSERT INTO face_encodings (student_id, encoding) VALUES (?, ?)",
                     (student_id, np.asarray(enc, dtype=np.float64).tobytes()))
    conn.commit()


def load_encodings(conn, exclude_id=None):
    """Returns (array of shape (n,128), list of student_ids)."""
    rows = conn.execute("SELECT student_id, encoding FROM face_encodings").fetchall()
    ids, encs = [], []
    for r in rows:
        if exclude_id is not None and r["student_id"] == exclude_id:
            continue
        ids.append(r["student_id"])
        encs.append(np.frombuffer(r["encoding"], dtype=np.float64))
    if not encs:
        return np.empty((0, 128)), []
    return np.array(encs), ids


# ---------- sessions & attendance ----------
def record_session(conn, day, period):
    """Mark that attendance is being taken for this period (it now counts as 'held')."""
    conn.execute("INSERT OR IGNORE INTO sessions (date, period, started_at) VALUES (?, ?, ?)",
                 (day, period, datetime.now().strftime("%H:%M:%S")))
    conn.commit()


def set_status(conn, student_id, day, period, status, reason=""):
    """
    Save a student's status for one period. A 'Present' is never overwritten,
    but 'Absent' can be upgraded to 'Present' (e.g. failed liveness, then blinked properly).
    Returns True if the row was created/changed.
    """
    now = datetime.now().strftime("%H:%M:%S")
    cur = conn.execute(
        """INSERT INTO attendance (student_id, date, period, time, status, reason)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(student_id, date, period) DO UPDATE SET
               time=excluded.time, status=excluded.status, reason=excluded.reason
           WHERE attendance.status != 'Present'""",
        (student_id, day, period, now, status, reason))
    conn.commit()
    return cur.rowcount > 0


def period_records(conn, day, period):
    rows = conn.execute("SELECT student_id, status FROM attendance WHERE date=? AND period=?",
                        (day, period)).fetchall()
    return {r["student_id"]: r["status"] for r in rows}


# ---------- statistics ----------
def attendance_summary(conn):
    """
    Per-student numbers + overall meta.
      pct_so_far : present periods / periods held so far
      pct_year   : present periods / (TOTAL_WORKING_DAYS x PERIODS_PER_DAY)
    """
    periods_held = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    days_held = conn.execute("SELECT COUNT(DISTINCT date) FROM sessions").fetchone()[0]
    total_year = TOTAL_WORKING_DAYS * PERIODS_PER_DAY

    data = conn.execute(
        """SELECT s.student_id, s.name, s.class_name,
                  COUNT(CASE WHEN a.status = 'Present' THEN 1 END) AS present
           FROM students s LEFT JOIN attendance a ON a.student_id = s.student_id
           GROUP BY s.student_id ORDER BY s.student_id""").fetchall()

    rows = []
    for r in data:
        present = r["present"]
        rows.append({
            "student_id": r["student_id"], "name": r["name"], "class_name": r["class_name"],
            "present": present,
            "held": periods_held,
            "absent": max(periods_held - present, 0),
            "pct_so_far": round(present / periods_held * 100, 1) if periods_held else 0.0,
            "pct_year": round(present / total_year * 100, 2),
        })
    meta = {"periods_held": periods_held, "days_held": days_held,
            "total_year_periods": total_year,
            "days_remaining": max(TOTAL_WORKING_DAYS - days_held, 0)}
    return rows, meta
