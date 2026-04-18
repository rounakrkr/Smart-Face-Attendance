from flask import Flask, flash, jsonify, render_template, request, redirect
import mysql.connector
import threading
from ml.capture_and_mark import start_attendance_session
from datetime import datetime
import logging
import base64
import cv2
import numpy as np
import face_recognition
from io import BytesIO
from PIL import Image
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "your-secret-key-here"  # CHANGE IN PRODUCTION

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

attendance_running = False
attendance_stop_event = None

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "12345",
    "database": "SmartAttendance"
}

# Database connection
def make_connection():
    return mysql.connector.connect(**DB_CONFIG)

# Early warning check
def run_early_warning(cursor):
    cursor.execute("""
        SELECT session_date
        FROM class_sessions
        WHERE finalized = TRUE
        ORDER BY session_date DESC
        LIMIT 3
    """)
    last_dates = [row[0] for row in cursor.fetchall()]
    if len(last_dates) < 3:
        return

    cursor.execute("SELECT student_id, roll_no, warning_level FROM students")
    students = cursor.fetchall()

    for student_id, roll_no, warning_level in students:
        cursor.execute("""
            SELECT COUNT(DISTINCT date)
            FROM attendance
            WHERE student_id = %s AND date IN (%s, %s, %s)
        """, (student_id, last_dates[0], last_dates[1], last_dates[2]))
        present_count = cursor.fetchone()[0]

        if present_count == 0 and warning_level != 3:
            cursor.execute("""
                UPDATE students SET warning_level = 3 WHERE student_id = %s
            """, (student_id,))
            logger.info(f"Early warning triggered for roll no {roll_no}")

# User class
class User(UserMixin):
    def __init__(self, user_id, username, role, teacher_id=None, student_id=None):
        self.id = user_id
        self.username = username
        self.role = role
        self.teacher_id = teacher_id
        self.student_id = student_id

@login_manager.user_loader
def load_user(user_id):
    conn = make_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_data:
        return User(
            user_id=user_data['user_id'],
            username=user_data['username'],
            role=user_data['role'],
            teacher_id=user_data['teacher_id'],
            student_id=user_data['student_id']
        )
    return None

# Login/Logout
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = make_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(
                user_id=user_data['user_id'],
                username=user_data['username'],
                role=user_data['role'],
                teacher_id=user_data['teacher_id'],
                student_id=user_data['student_id']
            )
            login_user(user)
            if user.role == 'student':
                return redirect('/student')
            else:
                return redirect('/')
        else:
            return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

# Student dashboard
@app.route('/student')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        return "Unauthorized"

    student_id = current_user.student_id
    if not student_id:
        return "Student record not linked", 400

    conn = make_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT s.name, s.roll_no, c.class_name
        FROM students s
        LEFT JOIN classes c ON s.class_id = c.class_id
        WHERE s.student_id = %s
    """, (student_id,))
    student = cursor.fetchone()
    if not student:
        return "Student not found", 404

    cursor.execute("""
        SELECT 
            COUNT(a.attendance_id) AS present_classes,
            (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE) AS total_classes,
            CASE
                WHEN (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE) = 0 THEN 0
                ELSE ROUND(
                    (COUNT(a.attendance_id) / 
                    (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE)) * 100, 2
                )
            END AS attendance_percentage
        FROM students s
        LEFT JOIN attendance a ON s.student_id = a.student_id
        WHERE s.student_id = %s
    """, (student_id,))
    summary = cursor.fetchone()
    for key in ['present_classes', 'total_classes', 'attendance_percentage']:
        if summary[key] is None:
            summary[key] = 0

    cursor.execute("""
        SELECT date, time, status
        FROM attendance
        WHERE student_id = %s
        ORDER BY date DESC, time DESC
    """, (student_id,))
    records = cursor.fetchall()
    for record in records:
        if record['time']:
            total_seconds = int(record['time'].total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            record['time_str'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            record['time_str'] = '-'

    cursor.close()
    conn.close()
    return render_template('student_dashboard.html', student=student, summary=summary, records=records)

# Student password change
@app.route('/student/profile', methods=['GET', 'POST'])
@login_required
def student_profile():
    if current_user.role != 'student':
        return "Unauthorized"

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_password or not new_password or not confirm_password:
            flash('All fields are required')
            return redirect('/student/profile')

        if new_password != confirm_password:
            flash('New passwords do not match')
            return redirect('/student/profile')

        conn = make_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password_hash FROM users WHERE user_id = %s", (current_user.id,))
        user_data = cursor.fetchone()
        cursor.close()
        if not user_data or not check_password_hash(user_data['password_hash'], current_password):
            flash('Current password is incorrect')
            conn.close()
            return redirect('/student/profile')

        new_hash = generate_password_hash(new_password)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (new_hash, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Password changed successfully')
        return redirect('/student')

    return render_template('student_profile.html')

# Teacher/Admin dashboard
@app.route('/')
@login_required
def dashboard():
    return render_template("dashboard.html")

# API: Recent attendance
@app.route('/api/recent_attendance')
def recent_attendance():
    conn = make_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT a.time, s.name, a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.student_id
            WHERE a.date = CURDATE()
            ORDER BY a.time DESC
            LIMIT 5
        """)
        rows = cursor.fetchall()
        result = []
        for row in rows:
            total_seconds = int(row[0].total_seconds())
            hours = (total_seconds // 3600) % 24
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            time_obj = datetime.strptime(f"{hours:02d}:{minutes:02d}:{seconds:02d}", "%H:%M:%S").time()
            time_str = time_obj.strftime("%I:%M:%S %p")
            result.append({"time": time_str, "name": row[1], "status": row[2]})
        return jsonify(result)
    except Exception as e:
        logger.error(f"recent_attendance error: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        cursor.close()
        conn.close()

# API: Attendance summary (filtered by role)
@app.route('/api/attendance_summary')
@login_required
def attendance_summary():
    conn = make_connection()
    cursor = conn.cursor(dictionary=True)

    where_clause = ""
    params = []

    if current_user.role == 'teacher':
        cursor.execute("SELECT class_id FROM teachers WHERE teacher_id = %s", (current_user.teacher_id,))
        teacher_class = cursor.fetchone()
        if not teacher_class:
            return jsonify({"error": "Teacher not assigned to any class"}), 400
        where_clause = "WHERE s.class_id = %s"
        params.append(teacher_class['class_id'])
    elif current_user.role == 'admin':
        where_clause = ""
    else:
        return jsonify({"error": "Unauthorized"})

    query = f"""
        SELECT 
            s.student_id,
            s.roll_no,
            s.name,
            s.warning_level,
            COUNT(a.attendance_id) AS present_classes,
            (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE) AS total_classes,
            CASE
                WHEN (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE) = 0 THEN 0
                ELSE ROUND(
                    (COUNT(a.attendance_id) / 
                    (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE)) * 100, 2
                )
            END AS attendance_percentage,
            CASE
                WHEN (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE) >= 10
                    AND (
                        CASE
                            WHEN (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE) = 0 THEN 0
                            ELSE (COUNT(a.attendance_id) / 
                                (SELECT COUNT(DISTINCT session_date) FROM class_sessions WHERE finalized = TRUE)) * 100
                        END
                    ) < 75
                THEN 'At Risk'
                ELSE 'Safe'
            END AS status
        FROM students s
        LEFT JOIN attendance a ON s.student_id = a.student_id
        {where_clause}
        GROUP BY s.student_id, s.roll_no, s.name, s.warning_level
    """
    cursor.execute(query, params)
    rows = cursor.fetchall()

    students_data = []
    student_ids = []
    for row in rows:
        students_data.append({
            'student_id': row['student_id'],
            'roll_no': row['roll_no'],
            'name': row['name'],
            'warning_level': row['warning_level'],
            'present': row['present_classes'],
            'total': row['total_classes'],
            'percentage': row['attendance_percentage'],
            'status': row['status']
        })
        student_ids.append(row['student_id'])

    total_students = len(students_data)

    if student_ids:
        placeholders = ','.join(['%s'] * len(student_ids))
        cursor.execute(f"""
            SELECT COUNT(DISTINCT student_id) AS cnt
            FROM attendance
            WHERE date = CURDATE() AND student_id IN ({placeholders})
        """, student_ids)
        present_today = cursor.fetchone()['cnt']
    else:
        present_today = 0

    early_warning = sum(1 for s in students_data if s['warning_level'] >= 3)
    detention_risk = sum(1 for s in students_data if s['status'] == 'At Risk')

    cursor.close()
    conn.close()
    return jsonify({
        'students': students_data,
        'total_students': total_students,
        'present_today': present_today,
        'early_warning': early_warning,
        'detention_risk': detention_risk
    })

# Attendance session control
@app.route("/attendance_status")
def attendance_status():
    return jsonify({"running": attendance_running})

@app.route("/start_attendance", methods=["POST"])
def start_attendance():
    global attendance_running, attendance_stop_event
    if attendance_running:
        return jsonify({"status": "already_running"}), 409

    attendance_stop_event = threading.Event()

    def run_in_background():
        global attendance_running, attendance_stop_event
        attendance_running = True
        try:
            start_attendance_session(stop_event=attendance_stop_event)
        except Exception as e:
            logger.error(f"Attendance session error: {e}")
        finally:
            attendance_running = False
            attendance_stop_event = None

    threading.Thread(target=run_in_background, daemon=True).start()
    return jsonify({"status": "started"}), 202

@app.route("/stop_attendance", methods=["POST"])
def stop_attendance():
    global attendance_stop_event
    if not attendance_running or not attendance_stop_event:
        return jsonify({"status": "no_active_session"}), 400
    attendance_stop_event.set()
    return jsonify({"status": "stopping"}), 200

@app.route("/finalize_class")
def finalize_class():
    conn = make_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE class_sessions
            SET finalized = TRUE
            WHERE session_date = CURDATE()
        """)
        run_early_warning(cursor)
        conn.commit()
        return jsonify({"status": "class finalized", "early_warning_executed": True})
    except Exception as e:
        logger.error(f"Error finalizing class: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        cursor.close()
        conn.close()

# Student registration (face + auto user)
@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if current_user.role not in ['admin', 'teacher']:
        return "Unauthorized"

    if request.method == 'GET':
        conn = make_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
        classes = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('register.html', classes=classes)

    data = request.get_json()
    roll_no = data.get('roll_no')
    name = data.get('name')
    class_id = data.get('class_id')
    image_data = data.get('image')

    if not all([roll_no, name, class_id, image_data]):
        return jsonify({'success': False, 'error': 'Missing fields'}), 400

    try:
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        img_bytes = base64.b64decode(image_data)
        img = Image.open(BytesIO(img_bytes))
        img = np.array(img)
    except Exception as e:
        logger.error(f"Image decode error: {e}")
        return jsonify({'success': False, 'error': 'Invalid image'}), 400

    if len(img.shape) != 3:
        return jsonify({'success': False, 'error': 'Image must be RGB'}), 400

    face_locations = face_recognition.face_locations(img)
    if len(face_locations) == 0:
        return jsonify({'success': False, 'error': 'No face detected'}), 400
    if len(face_locations) > 1:
        return jsonify({'success': False, 'error': 'Multiple faces detected'}), 400

    encodings = face_recognition.face_encodings(img, face_locations)
    if not encodings:
        return jsonify({'success': False, 'error': 'Could not encode face'}), 400

    encoding_str = np.array2string(encodings[0], separator=',', max_line_width=1000)

    conn = make_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT student_id FROM students WHERE roll_no = %s", (roll_no,))
        existing = cursor.fetchone()
        if existing:
            student_id = existing[0]
            cursor.execute("""
                UPDATE students
                SET name = %s, class_id = %s, face_encoding = %s
                WHERE student_id = %s
            """, (name, class_id, encoding_str, student_id))
            message = "Student updated successfully"
        else:
            cursor.execute("""
                INSERT INTO students (roll_no, name, class_id, face_encoding)
                VALUES (%s, %s, %s, %s)
            """, (roll_no, name, class_id, encoding_str))
            student_id = cursor.lastrowid
            message = "Student registered successfully"

        # Auto-create user account
        suffix = roll_no[-3:] if len(roll_no) >= 3 else roll_no
        default_password = f"student@{suffix}"
        password_hash = generate_password_hash(default_password)

        cursor.execute("SELECT user_id FROM users WHERE username = %s", (roll_no,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (username, password_hash, role, student_id)
                VALUES (%s, %s, 'student', %s)
            """, (roll_no, password_hash, student_id))

        conn.commit()
        return jsonify({
            'success': True,
            'message': message,
            'login_credentials': {'username': roll_no, 'password': default_password}
        })
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        return jsonify({'success': False, 'error': 'Database error'}), 500
    finally:
        cursor.close()
        conn.close()

# Admin panel
@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        return "Unauthorized"

    conn = make_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            u.user_id, u.username, u.role, u.created_at,
            t.name AS teacher_name, t.class_id,
            s.name AS student_name, s.class_id AS student_class_id,
            c.class_name
        FROM users u
        LEFT JOIN teachers t ON u.teacher_id = t.teacher_id
        LEFT JOIN students s ON u.student_id = s.student_id
        LEFT JOIN classes c ON c.class_id = COALESCE(t.class_id, s.class_id)
        ORDER BY u.created_at DESC
    """)
    users = cursor.fetchall()
    cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
    classes = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin.html', users=users, classes=classes)

@app.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        return "Unauthorized"

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        if not username or not password or not role:
            flash('Username, password, and role are required')
            return redirect('/admin/add_user')

        teacher_id = None
        student_id = None

        if role == 'teacher':
            teacher_name = request.form.get('teacher_name')
            teacher_email = request.form.get('teacher_email')
            class_id = request.form.get('class_id')
            if not teacher_name or not class_id:
                flash('Teacher name and class are required')
                return redirect('/admin/add_user')

            conn = make_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT teacher_id FROM teachers WHERE class_id = %s", (class_id,))
            if cursor.fetchone():
                flash('This class already has a teacher')
                cursor.close()
                conn.close()
                return redirect('/admin/add_user')
            cursor.execute("""
                INSERT INTO teachers (name, email, class_id)
                VALUES (%s, %s, %s)
            """, (teacher_name, teacher_email, class_id))
            teacher_id = cursor.lastrowid
            conn.commit()
            cursor.close()
            conn.close()

        elif role == 'student':
            student_id = request.form.get('student_id')
            if not student_id:
                flash('Please select a student to link')
                return redirect('/admin/add_user')

        password_hash = generate_password_hash(password)
        conn = make_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (username, password_hash, role, teacher_id, student_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, password_hash, role, teacher_id, student_id))
            conn.commit()
            flash('User added successfully')
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}')
        finally:
            cursor.close()
            conn.close()
        return redirect('/admin')

    conn = make_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT student_id, name, roll_no FROM students ORDER BY name")
    students = cursor.fetchall()
    cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
    classes = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('add_user.html', students=students, classes=classes)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return "Unauthorized"

    conn = make_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        conn.commit()
        flash('User deleted')
    except Exception as e:
        conn.rollback()
        flash(f'Error: {str(e)}')
    finally:
        cursor.close()
        conn.close()
    return redirect('/admin')

if __name__ == "__main__":
    app.run(debug=True)