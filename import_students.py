"""
Step 0: Load the class roster (students.csv) into the database.
Edit students.csv first, then run:  python import_students.py
Safe to re-run: existing students are updated, new ones are added.
"""

import csv
from database import get_conn


def import_students(csv_file="students.csv"):
    conn = get_conn()
    count = 0
    with open(csv_file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = row["student_id"].strip()
            if not sid:
                continue
            conn.execute(
                """INSERT INTO students (student_id, name, class_name, parent_email)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(student_id) DO UPDATE SET
                       name=excluded.name, class_name=excluded.class_name,
                       parent_email=excluded.parent_email""",
                (sid, row["name"].strip(), row.get("class_name", "").strip(),
                 row.get("parent_email", "").strip()),
            )
            count += 1
    conn.commit()
    conn.close()
    print(f"[INFO] Imported/updated {count} students from {csv_file}")


if __name__ == "__main__":
    import_students()
