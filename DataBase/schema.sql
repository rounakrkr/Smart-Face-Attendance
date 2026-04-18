CREATE DATABASE SmartAttendance;

USE SmartAttendance;

-- 1. Classes
CREATE TABLE classes (
    class_id INT AUTO_INCREMENT PRIMARY KEY,
    class_name VARCHAR(20) NOT NULL UNIQUE
);

-- 2. Students (no course column)
CREATE TABLE students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    roll_no VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    class_id INT,
    face_encoding TEXT,
    warning_level INT DEFAULT 0,
    FOREIGN KEY (class_id) REFERENCES classes(class_id) ON DELETE SET NULL
);

-- 3. Teachers (linked to class)
CREATE TABLE teachers (
    teacher_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    class_id INT UNIQUE,
    FOREIGN KEY (class_id) REFERENCES classes(class_id) ON DELETE SET NULL
);

-- 4. Users (login accounts)
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'teacher', 'student') NOT NULL,
    teacher_id INT NULL,
    student_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
);

-- 5. Attendance
CREATE TABLE attendance (
    attendance_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    date DATE NOT NULL,
    time TIME,
    status VARCHAR(10),
    match_confidence FLOAT,
    method VARCHAR(10),
    face_detected BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
    UNIQUE KEY unique_attendance_per_day (student_id, date)
);

-- 6. Class sessions (for early warning and total classes)
CREATE TABLE class_sessions (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    session_date DATE UNIQUE NOT NULL,
    finalized BOOLEAN DEFAULT FALSE
);

-- Optional: Insert sample classes (1st to 10th)
INSERT INTO classes (class_name) VALUES
('1A'), ('2A'), ('3A'), ('4A'), ('5A'),
('6A'), ('7A'), ('8A'), ('9A'), ('10A');

-- Optional: Insert admin user (change password hash as needed)
INSERT INTO users (username, password_hash, role) VALUES
('admin', 'scrypt:32768:8:1$tJ3V1nn1dpJnpEnT$46131aeb5b0040754c7a0227befe0cbe1071c577a33f0704ad03486b9d147c7df9a88af4a98e2481f8eae5d50dc9c84da36f7487a5d8c68ff95afcc5acba8d53', 'admin');