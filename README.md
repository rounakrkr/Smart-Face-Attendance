# 🚀 Smart Attendance Portal (Face Recognition)

A high-performance, real-time **Smart Attendance System** built using Python, Flask, and Computer Vision. This project was awarded a **10/10 grade** for its robust architecture and real-world utility! 🎓🏆

## 🔥 Overview
This portal automates the traditional attendance process using Face Recognition. It doesn't just mark attendance; it provides actionable insights through a live dashboard, helping teachers identify "at-risk" students early.

## ✨ Key Features
* **👤 Face Recognition:** Uses 128-dimensional embeddings for high accuracy.
* **⏱️ Stability Logic:** Ensures a face is stable for 0.8s before marking attendance (prevents accidental logs).
* **📊 Live Dashboard:** Real-time summary cards for Today's Attendance, Detention Risk, and Early Warnings.
* **⚠️ Early Warning System:** Automatically flags students missing 3 consecutive classes.
* **🔐 Role-Based Access:** Separate logins for Admin, Teacher, and Students.
* **⚡ AJAX Polling:** Dashboard updates live without needing to refresh the page.

## 🛠️ Tech Stack
- **Language:** Python 3.x 🐍
- **ML/CV:** OpenCV, dlib, face_recognition
- **Backend:** Flask (Python)
- **Database:** MySQL 🗄️
- **Frontend:** HTML5, CSS3, JavaScript (Vanilla)

## 🗂️ Database Design
The system uses a relational schema to ensure data integrity:
- `students`: Stores profile and face encodings.
- `attendance`: Transactional logs of student presence.
- `class_sessions`: Tracks total classes conducted (crucial for accurate % calculation).
- `users`: Manages authentication and roles.

## 🎯 Final Verdict
This system is designed to be scalable for schools and coaching centers, bridging the gap between raw AI and practical management tools.
