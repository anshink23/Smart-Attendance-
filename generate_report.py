"""
Excel report + chart + defaulter list.
Run: python generate_report.py
Creates attendance_report.xlsx (Summary + Daily log sheets) and attendance_chart.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from config import DEFAULTER_THRESHOLD, PERIODS_PER_DAY, TOTAL_WORKING_DAYS
from database import attendance_summary, get_conn


def make_report():
    conn = get_conn()
    rows, meta = attendance_summary(conn)
    log = pd.read_sql_query(
        """SELECT a.date, a.period, s.student_id, s.name, s.class_name, a.status, a.time, a.reason
           FROM attendance a JOIN students s ON s.student_id = a.student_id
           ORDER BY a.date, a.period, s.student_id""", conn)
    conn.close()

    if meta["periods_held"] == 0:
        print("[INFO] No attendance recorded yet. Run mark_attendance.py first.")
        return

    summary = pd.DataFrame(rows).rename(columns={
        "present": "periods_present", "held": "periods_held", "absent": "periods_absent",
        "pct_so_far": "attendance_pct_so_far",
        "pct_year": f"attendance_pct_of_{TOTAL_WORKING_DAYS}_days"})

    print(f"\n=== Attendance Summary ===")
    print(f"Working days held: {meta['days_held']} of {TOTAL_WORKING_DAYS} "
          f"({meta['days_remaining']} remaining) | periods held: {meta['periods_held']} "
          f"of {meta['total_year_periods']}")
    print(summary.to_string(index=False))

    with pd.ExcelWriter("attendance_report.xlsx") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        log.to_excel(writer, sheet_name="Daily log", index=False)
    print("\n[INFO] Excel report saved to attendance_report.xlsx")

    plt.figure(figsize=(8, 5))
    plt.bar(summary["name"], summary["attendance_pct_so_far"], color="teal")
    plt.axhline(DEFAULTER_THRESHOLD, color="red", linestyle="--",
                label=f"{DEFAULTER_THRESHOLD:.0f}% minimum")
    plt.ylabel("Attendance % (periods held so far)")
    plt.title("Student Attendance Percentage")
    plt.xticks(rotation=30, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig("attendance_chart.png")
    print("[INFO] Chart saved to attendance_chart.png")

    low = summary[summary["attendance_pct_so_far"] < DEFAULTER_THRESHOLD]
    if low.empty:
        print("\n[INFO] No defaulters.")
    else:
        print(f"\n[WARNING] Defaulters (below {DEFAULTER_THRESHOLD:.0f}% so far):")
        print(low[["student_id", "name", "attendance_pct_so_far"]].to_string(index=False))


if __name__ == "__main__":
    make_report()
