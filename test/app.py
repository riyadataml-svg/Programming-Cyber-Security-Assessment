from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import json
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super-pro-security-key-9281'

# Static Admin Credentials (ADMIN: Admin, PASSWORD: Admin@123)
ADMIN_USERNAME = "Admin"
ADMIN_PASSWORD_HASH = generate_password_hash("Admin@123")

# Security Decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Database Setup
def get_db():
    conn = sqlite3.connect('assessment.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL, course TEXT NOT NULL, test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.execute('CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, score INTEGER, percentage REAL, grade TEXT, FOREIGN KEY(student_id) REFERENCES students(id))')
    conn.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT, course TEXT NOT NULL, level TEXT NOT NULL, question_text TEXT NOT NULL, option1 TEXT NOT NULL, option2 TEXT NOT NULL, option3 TEXT NOT NULL, option4 TEXT NOT NULL, correct_answer TEXT NOT NULL)')
    count = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    if count == 0: seed_questions(conn)
    conn.commit()
    conn.close()

def seed_questions(conn):
    initial_data = [
        ("Python", "Level 1", "What is output of 2**3?", "6", "8", "9", "12", "8"),
        ("Python", "Level 1", "Mutable data type?", "Tuple", "String", "List", "Integer", "List"),
        ("MySQL", "Level 1", "Fetch data command?", "GET", "SELECT", "EXTRACT", "FETCH", "SELECT"),
        ("Cyber Security", "Level 1", "What is Phishing?", "Fishing", "Fraudulent Info", "Protocol", "Encryption", "Fraudulent Info")
    ]
    conn.executemany('INSERT INTO questions (course, level, question_text, option1, option2, option3, option4, correct_answer) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', initial_data)

@app.route('/')
def home(): return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    name, email, course = request.form.get('name'), request.form.get('email'), request.form.get('course')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO students (name, email, course) VALUES (?, ?, ?)', (name, email, course))
    student_id = cursor.lastrowid
    conn.commit()
    conn.close()
    session['student_id'], session['student_name'], session['course'] = student_id, name, course
    session['level'], session['total_score'] = "Level 1", 0
    return redirect(url_for('test_page'))

@app.route('/test')
def test_page():
    if 'student_id' not in session: return redirect(url_for('home'))
    course, current_level = session['course'], session['level']
    conn = get_db()
    db_questions = conn.execute('SELECT * FROM questions WHERE course = ? AND level = ?', (course, current_level)).fetchall()
    conn.close()
    questions = [{"id": q['id'], "question": q['question_text'], "options": [q['option1'], q['option2'], q['option3'], q['option4']], "answer": q['correct_answer']} for q in db_questions]
    return render_template('test.html', questions=questions, course=course, level=current_level)

@app.route('/submit_test', methods=['POST'])
def submit_test():
    if 'student_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    answers = request.json.get('answers', {})
    course, current_level = session['course'], session['level']
    conn = get_db()
    db_questions = conn.execute('SELECT id, correct_answer FROM questions WHERE course = ? AND level = ?', (course, current_level)).fetchall()
    score = sum(1 for q in db_questions if str(q['id']) in answers and answers[str(q['id'])] == q['correct_answer'])
    session['total_score'] += score
    if current_level == "Level 1":
        session['level'] = "Level 2"; conn.close()
        return jsonify({'redirect': url_for('test_page'), 'next_level': True})
    else:
        percentage = (session['total_score'] / 10.0) * 100
        grade = 'A' if percentage >= 80 else 'B' if percentage >= 60 else 'C' if percentage >= 40 else 'F'
        conn.execute('INSERT INTO results (student_id, score, percentage, grade) VALUES (?, ?, ?, ?)', (session['student_id'], session['total_score'], percentage, grade))
        conn.commit(); conn.close()
        return jsonify({'redirect': url_for('result_page')})

@app.route('/result')
def result_page():
    if 'student_id' not in session: return redirect(url_for('home'))
    conn = get_db()
    result = conn.execute('SELECT s.name, s.course, r.score, r.percentage, r.grade FROM students s JOIN results r ON s.id = r.student_id WHERE s.id = ? ORDER BY r.id DESC LIMIT 1', (session['student_id'],)).fetchone()
    conn.close()
    return render_template('result.html', result=result)

# --- ADMIN SECURITY ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        if user == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, pwd):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error="Invalid Credentials")
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('home'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    questions = conn.execute('SELECT * FROM questions ORDER BY course, level').fetchall()
    conn.close()
    return render_template('admin.html', questions=questions)

@app.route('/admin/add', methods=['POST'])
@admin_required
def admin_add_question():
    course, level, text, ans = request.form.get('course'), request.form.get('level'), request.form.get('question_text'), request.form.get('correct_answer')
    o1, o2, o3, o4 = request.form.get('o1'), request.form.get('o2'), request.form.get('o3'), request.form.get('o4')
    conn = get_db()
    conn.execute('INSERT INTO questions (course, level, question_text, option1, option2, option3, option4, correct_answer) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (course, level, text, o1, o2, o3, o4, ans))
    conn.commit(); conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:id>')
@admin_required
def admin_delete_question(id):
    conn = get_db()
    conn.execute('DELETE FROM questions WHERE id = ?', (id,))
    conn.commit(); conn.close()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001, host='0.0.0.0')
