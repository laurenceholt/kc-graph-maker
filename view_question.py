#!/usr/bin/env python3
"""
Quick viewer: fetch a question image from the database and open it.

Usage:
    python view_question.py                     # list all questions
    python view_question.py 1 3                 # view Assessment 1, Q3
    python view_question.py 2 7                 # view Assessment 2, Q7
"""
import sys
import os
import subprocess
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

if len(sys.argv) < 3:
    # List all questions
    cur.execute("""
        SELECT grade, module, topic, assessment_number, question_number,
               image_width, image_height, length(image_data)/1024 as kb
        FROM questions ORDER BY filename, assessment_number, question_number
    """)
    print("Available questions:\n")
    print(f"  Grade  Mod   Topic  Assess  Q#   Dims            Size")
    print(f"  {'─'*55}")
    for r in cur.fetchall():
        topic = r[2] or "-"
        print(f"  {r[0]:<6} {r[1]:<5} {topic:<6} {r[3]:<7} {r[4]:<4} {r[5]}x{r[6]:<6}  {r[7]} KB")
    print(f"\nUsage: python view_question.py <assessment#> <question#>")
else:
    assess = int(sys.argv[1])
    qnum = int(sys.argv[2])

    cur.execute("""
        SELECT image_data, grade, module, topic, filename
        FROM questions
        WHERE assessment_number = %s AND question_number = %s
        LIMIT 1
    """, (assess, qnum))
    row = cur.fetchone()

    if not row:
        print(f"No question found for Assessment {assess}, Q{qnum}")
        sys.exit(1)

    img_data, grade, module, topic, filename = row
    out_path = f"/tmp/assess{assess}_q{qnum}.png"

    with open(out_path, "wb") as f:
        f.write(img_data)

    topic_str = f", Topic {topic}" if topic else ""
    print(f"Assessment {assess}, Q{qnum} — {grade} {module}{topic_str}")
    print(f"Source: {filename}")
    print(f"Saved to {out_path}")

    # Open in Preview on macOS
    subprocess.run(["open", out_path])

conn.close()
