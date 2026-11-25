"""
Email parents of students who were ABSENT in any period today.
Set credentials first (Gmail App Password, not your normal password):
    PowerShell:  $env:SENDER_EMAIL="you@gmail.com"
                 $env:SENDER_APP_PASSWORD="your16charapppassword"
Run: python send_absentee_alerts.py
"""

import os
import smtplib
from collections import defaultdict
from datetime import date
from email.mime.text import MIMEText

from config import PERIODS_PER_DAY, is_working_day
from database import get_conn

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD", "")


def send_email(to_email, student, periods, held):
    plist = ", ".join(str(p) for p in periods)
    body = (f"Dear Parent,\n\n"
            f"Your ward {student['name']} (ID: {student['student_id']}, Class: {student['class_name']}) "
            f"was marked ABSENT on {date.today().isoformat()} in period(s) {plist} "
            f"({len(periods)} of {held} periods held today).\n\n"
            f"Regards,\nSchool Attendance System")
    msg = MIMEText(body)
    msg["Subject"] = f"Absence Alert - {student['name']}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        server.send_message(msg)


def notify_absentees():
    today = date.today()
    if not is_working_day(today):
        print(f"[INFO] {today.strftime('%A')} is not a school day.")
        return
    if not SENDER_EMAIL or not SENDER_APP_PASSWORD:
        print("[ERROR] Set SENDER_EMAIL and SENDER_APP_PASSWORD environment variables first.")
        return

    day = today.isoformat()
    conn = get_conn()
    held = conn.execute("SELECT COUNT(*) FROM sessions WHERE date=?", (day,)).fetchone()[0]
    rows = conn.execute(
        """SELECT s.*, a.period FROM attendance a
           JOIN students s ON s.student_id = a.student_id
           WHERE a.date=? AND a.status='Absent' ORDER BY s.student_id, a.period""", (day,)).fetchall()
    conn.close()

    if not rows:
        print("[INFO] No absentees today.")
        return

    students, periods = {}, defaultdict(list)
    for r in rows:
        students[r["student_id"]] = r
        periods[r["student_id"]].append(r["period"])

    for sid, s in students.items():
        if not s["parent_email"]:
            print(f"[WARN] No parent email for {s['name']} ({sid})")
            continue
        try:
            send_email(s["parent_email"], s, periods[sid], held)
            print(f"[INFO] Alert sent for {s['name']} (periods {periods[sid]})")
        except Exception as e:
            print(f"[ERROR] Could not send for {s['name']}: {e}")


if __name__ == "__main__":
    notify_absentees()
