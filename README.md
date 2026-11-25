# Smart Classroom Attendance (8 periods/day, Face Recognition + Liveness)

* Students are added on a **web page** with ID, name and a face photo. The photo is analysed
  (exactly one clear face) and saved in the database.
* In class, the **webcam** compares the live face with the uploaded photo and checks for a real blink.
* Attendance is taken **per period (1-8)**. Saturdays and Sundays are skipped.
* Percentages are calculated against **600 working days x 8 periods = 4800 periods**, and also "so far".

| Situation (per period) | Result |
|---|---|
| Live face matches uploaded photo + blink | Present |
| Face matches but no blink in 8 s (photo/screen) | Absent (liveness failed) |
| Face not recognized by the end of the period | Absent |

## Setup (once)
    python -m pip install flask
Put `shape_predictor_68_face_landmarks.dat` in this folder. Edit `config.py` for period timings,
600 working days, 75% threshold, etc.

## Daily use
1. `python dashboard.py` -> open http://127.0.0.1:5000 -> **Students** page: add each student (ID, name, photo).
2. In a second terminal: `python mark_attendance.py --period 3` (or no `--period` to use the timetable in
   config.py). Students blink at the camera. Press `q` to end the period.
3. View results in the browser: **Daily** (P1-P8 grid) and **Summary** (percentages, defaulters).
4. `python generate_report.py` -> Excel (Summary + Daily log) and chart.
5. `python send_absentee_alerts.py` -> parents of students absent today (set SENDER_EMAIL / SENDER_APP_PASSWORD).

## Files no longer used
`register_faces.py`, `encode_faces.py`, `encodings.pickle` and the `dataset` folder were replaced by the web upload.
Old attendance data is kept in a table called `attendance_old` automatically.

## Limits
Blink detection stops printed photos and still screens, but a replayed video of someone blinking can pass.
Everything is stored in `attendance.db`; photo files are in `student_photos/` (file name saved in the database).
