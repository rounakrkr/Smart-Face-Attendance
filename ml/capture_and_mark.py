import cv2
import face_recognition
import numpy as np
import mysql.connector
from datetime import datetime, timedelta

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "12345",
    "database": "SmartAttendance"
}

def make_connection():
    """Create a database connection."""
    return mysql.connector.connect(**DB_CONFIG)

def load_known_faces(cursor):
    """Load all registered face encodings from the database."""
    cursor.execute("""
        SELECT student_id, face_encoding
        FROM students
        WHERE face_encoding IS NOT NULL
    """)
    known_ids = []
    known_encodings = []
    for student_id, encoding_str in cursor.fetchall():
        encoding = np.fromstring(encoding_str.strip('[]'), sep=',', dtype=float)
        known_ids.append(student_id)
        known_encodings.append(encoding)
    return known_ids, known_encodings

def mark_attendance(student_id, confidence, method, face_detected, cursor, conn):
    """Insert attendance record, reset warning level, and ensure class session exists."""
    cursor.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE student_id = %s AND date = CURDATE()
    """, (student_id,))
    if cursor.fetchone()[0] > 0:
        return "Already marked today"

    cursor.execute("""
        INSERT INTO attendance
            (student_id, date, time, status, match_confidence, method, face_detected)
        VALUES (%s, CURDATE(), CURTIME(), 'Present', %s, %s, %s)
    """, (student_id, confidence, method, face_detected))

    cursor.execute("""
        UPDATE students
        SET warning_level = 0
        WHERE student_id = %s
    """, (student_id,))

    cursor.execute("""
        INSERT IGNORE INTO class_sessions (session_date, finalized)
        VALUES (CURDATE(), FALSE)
    """)

    conn.commit()
    return "Attendance marked successfully"

def run_camera_and_mark(stop_event=None):
    """Main camera loop: detect faces, match, mark attendance."""
    conn = make_connection()
    cursor = conn.cursor()

    known_ids, known_encodings = load_known_faces(cursor)

    if len(known_encodings) == 0:
        print("No registered faces found")
        return

    cap = cv2.VideoCapture(0)
    STABILITY_SECONDS = 0.8
    ATTENDANCE_DURATION_MINUTES = 15
    THRESHOLD = 0.50

    session_start = datetime.now()
    marked_this_session = set()
    detection_start_times = {}

    print("Camera started. Press 'q' to quit.")

    cv2.namedWindow("Face Attendance", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Face Attendance", cv2.WND_PROP_TOPMOST, 1)

    while True:
        if stop_event and stop_event.is_set():
            print("Stop signal received. Ending session.")
            break

        ret, frame = cap.read()
        if not ret:
            break

        small_frame = cv2.resize(frame, (0, 0), fx=0.30, fy=0.30)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small)
        scale = 1 / 0.30
        now = datetime.now()

        if len(face_locations) > 0:
            if "face" not in detection_start_times:
                detection_start_times["face"] = now

            elapsed = (now - detection_start_times["face"]).total_seconds()

            for (top, right, bottom, left) in face_locations:
                top = int(top * scale)
                right = int(right * scale)
                bottom = int(bottom * scale)
                left = int(left * scale)

                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

                remaining = STABILITY_SECONDS - elapsed
                if remaining > 0:
                    cv2.putText(
                        frame,
                        f"Hold: {remaining:.1f}s",
                        (left, bottom + 25),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 255),
                        2
                    )
                else:
                    encodings = face_recognition.face_encodings(rgb_small, face_locations)

                    for face_encoding in encodings:
                        distances = face_recognition.face_distance(known_encodings, face_encoding)
                        best_match_index = np.argmin(distances)
                        best_distance = distances[best_match_index]

                        if best_distance < THRESHOLD:
                            student_id = known_ids[best_match_index]
                            if student_id not in marked_this_session:
                                result = mark_attendance(
                                    student_id,
                                    float(best_distance),
                                    'face',
                                    True,
                                    cursor,
                                    conn
                                )
                                marked_this_session.add(student_id)
                                print(f"Student {student_id} → {result}")
                                detection_start_times.pop("face", None)
                                break
        else:
            detection_start_times.pop("face", None)

        cv2.imshow("Face Attendance", frame)

        if datetime.now() - session_start > timedelta(minutes=ATTENDANCE_DURATION_MINUTES):
            print("Attendance window closed.")
            break

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    cursor.close()
    conn.close()

def start_attendance_session(stop_event=None):
    run_camera_and_mark(stop_event)