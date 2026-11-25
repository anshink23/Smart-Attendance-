"""
Take attendance for ONE period using the webcam.

For every student in the roster (faces come from the photos uploaded in the dashboard):
  * live webcam face matches the student AND blinks  -> PRESENT
  * face recognized but no blink in time (photo/screen) -> ABSENT
  * face never recognized before the period ends       -> ABSENT
Nothing is recorded on Saturdays and Sundays.

Run:  python mark_attendance.py                 (period picked from the timetable in config.py)
      python mark_attendance.py --period 3
      python mark_attendance.py --period 3 --minutes 10
Press 'q' in the camera window to end the period.
"""

import argparse
import time
from datetime import date

import cv2
import face_recognition
import numpy as np

from config import (FACE_LOST_RESET, FACE_TOLERANCE, LIVENESS_TIMEOUT, PERIODS_PER_DAY,
                    REQUIRED_BLINKS, current_period, is_working_day)
from database import (get_all_students, get_conn, load_encodings, period_records,
                      record_session, set_status)
from liveness_detection import BlinkCounter

GREEN, YELLOW, RED = (0, 255, 0), (0, 255, 255), (0, 0, 255)


def finalize_absentees(conn, day, period, roster):
    recorded = period_records(conn, day, period)
    count = 0
    for sid, name in roster.items():
        if sid not in recorded:
            set_status(conn, sid, day, period, "Absent", "Face not recognized in this period")
            print(f"[ABSENT] {name} ({sid}) - face not recognized")
            count += 1
    return count


def run(period=None, minutes=None):
    today = date.today()
    if not is_working_day(today):
        print(f"[INFO] Today is {today.strftime('%A')} - no classes. "
              f"Attendance is not taken on Saturdays and Sundays.")
        return

    if period is None:
        period = current_period()
        if period is None:
            print("[ERROR] No period is running right now according to PERIOD_TIMES in config.py.\n"
                  "        Choose one yourself, e.g.:  python mark_attendance.py --period 3")
            return
    if not 1 <= period <= PERIODS_PER_DAY:
        print(f"[ERROR] Period must be between 1 and {PERIODS_PER_DAY}.")
        return

    day = today.isoformat()
    conn = get_conn()
    known, known_ids = load_encodings(conn)
    if len(known) == 0:
        print("[ERROR] No registered faces yet. Run 'python dashboard.py', open the Students "
              "page and upload each student's photo first.")
        return

    roster = {s["student_id"]: s["name"] for s in get_all_students(conn)}
    missing = [f"{n} ({i})" for i, n in roster.items() if i not in set(known_ids)]
    if missing:
        print(f"[WARN] No face photo for: {', '.join(missing)} - they will be marked Absent.")

    record_session(conn, day, period)
    present = {sid for sid, st in period_records(conn, day, period).items() if st == "Present"}
    flagged = set()
    state = {}
    end_time = time.time() + minutes * 60 if minutes else None

    video = cv2.VideoCapture(0)
    print(f"[INFO] {today.strftime('%A %d-%m-%Y')} - Period {period}. "
          f"Each student: look at the camera and BLINK. Press 'q' to end.")

    while True:
        ret, frame = video.read()
        if not ret:
            break
        now = time.time()

        small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        boxes = face_recognition.face_locations(rgb_small, model="hog")
        encodings = face_recognition.face_encodings(rgb_small, boxes)

        for encoding, small_box in zip(encodings, boxes):
            distances = face_recognition.face_distance(known, encoding)
            best = int(np.argmin(distances))
            sid = known_ids[best] if distances[best] <= FACE_TOLERANCE else None
            box = tuple(v * 2 for v in small_box)           # (top, right, bottom, left)
            top, right, bottom, left = box

            if sid is None or sid not in roster:
                label, color = "Unknown", RED
            else:
                name = roster[sid]
                st = state.setdefault(sid, {"counter": BlinkCounter(), "since": now, "last_seen": now})
                if now - st["last_seen"] > FACE_LOST_RESET:
                    st["since"] = now
                st["last_seen"] = now

                if sid in present:
                    label, color = f"{name} - Present", GREEN
                else:
                    blinks = st["counter"].update(gray, box)
                    if blinks >= REQUIRED_BLINKS:
                        set_status(conn, sid, day, period, "Present", "Recognized + live")
                        present.add(sid)
                        flagged.discard(sid)
                        print(f"[PRESENT] {name} ({sid})")
                        label, color = f"{name} - Present", GREEN
                    elif now - st["since"] > LIVENESS_TIMEOUT:
                        if sid not in flagged:
                            set_status(conn, sid, day, period, "Absent", "Liveness check failed (no blink)")
                            flagged.add(sid)
                            print(f"[ABSENT] {name} ({sid}) - no live blink (possible photo/video)")
                        label, color = f"{name} - NOT LIVE (Absent)", RED
                    else:
                        left_s = int(LIVENESS_TIMEOUT - (now - st["since"]))
                        label, color = f"{name} - Blink now ({left_s}s)", YELLOW

            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.putText(frame, label, (left, max(top - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.putText(frame, f"Period {period} | Present {len(present)}/{len(roster)} | q = end",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.imshow("Smart Attendance System", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        if end_time and now >= end_time:
            print("[INFO] Time is over for this period.")
            break

    video.release()
    cv2.destroyAllWindows()

    n = finalize_absentees(conn, day, period, roster)
    print(f"[INFO] Period {period} saved. Present: {len(present)}, "
          f"marked absent (not recognized): {n}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=int, default=None, help="period number 1-8")
    ap.add_argument("--minutes", type=float, default=None, help="auto-end after N minutes")
    args = ap.parse_args()
    run(args.period, args.minutes)
