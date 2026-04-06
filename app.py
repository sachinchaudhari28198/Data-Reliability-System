import sys
import os
from flask import Flask, render_template, request, redirect, session
import psycopg2
import requests
import time
from urllib.parse import unquote

# Email
import smtplib
from email.mime.text import MIMEText

# Scheduler
from apscheduler.schedulers.background import BackgroundScheduler

# PDF
from reportlab.pdfgen import canvas

# Config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.config import DB_CONFIG, EMAIL_CONFIG

app = Flask(__name__)
app.secret_key = "secret123"

# SESSION CONFIG
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

# 🔥 GLOBAL STORES
last_result = {}
alerts_list = []

# ----------------------------
# 🔹 EMAIL + ALERT FUNCTION
# ----------------------------
def send_email_alert(subject, message):
    global alerts_list

    # ✅ Save alert for UI
    alerts_list.insert(0, message)
    alerts_list = alerts_list[:10]

    try:
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = EMAIL_CONFIG["sender"]
        msg['To'] = EMAIL_CONFIG["receiver"]

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_CONFIG["sender"], EMAIL_CONFIG["password"])
        server.send_message(msg)
        server.quit()

        print("✅ Email sent")

    except Exception as e:
        print("❌ Email Error:", e)


# ----------------------------
# 🔹 DATABASE FUNCTIONS
# ----------------------------
def get_total_records():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM posts;")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def get_chart_data():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT value FROM posts ORDER BY id DESC LIMIT 5;")
    data = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return data[::-1]


def get_chart2_data():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM posts WHERE status='Success';")
    success = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM posts WHERE status='Error';")
    error = cur.fetchone()[0]

    cur.close()
    conn.close()
    return [success, error]


def compute_health():
    success, error = get_chart2_data()
    total = success + error
    if total == 0:
        return "Low"
    return "Good" if (error / total) < 0.2 else "Low"


def get_history():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT url, status, response_time, score
        FROM history ORDER BY created_at DESC LIMIT 10;
    """)

    data = cur.fetchall()
    cur.close()
    conn.close()
    return data


def get_monitored_urls():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT url FROM monitored_urls;")
    urls = [row[0] for row in cur.fetchall()]

    cur.close()
    conn.close()
    return urls


def get_url_wise_data():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT url, response_time
        FROM history ORDER BY created_at ASC;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    data = {}
    for url, response_time in rows:
        if url not in data:
            data[url] = []
        data[url].append(round(response_time, 2))

    return data


# ----------------------------
# 🔥 AUTO MONITORING
# ----------------------------
def auto_check_urls():
    print("🔄 Auto Monitoring Running...")

    urls = get_monitored_urls()

    for url in urls:
        try:
            response = requests.get(url, timeout=5)

            if response.status_code != 200:
                send_email_alert("🚨 Auto Alert", f"URL Failed: {url}")

        except Exception as e:
            send_email_alert("🚨 Auto Alert", f"{url} Error: {str(e)}")


# ----------------------------
# 🔐 AUTH
# ----------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, password)
        )

        conn.commit()
        cur.close()
        conn.close()

        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password)
        )

        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            session['user'] = username
            return redirect('/dashboard')
        else:
            return "Invalid Login"

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


# ----------------------------
# HOME
# ----------------------------
@app.route('/')
def home():
    return render_template('home.html')


# ----------------------------
# DASHBOARD
# ----------------------------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')

    return render_template(
        'index.html',
        count=get_total_records(),
        health=compute_health(),
        chart_data=get_chart_data(),
        chart2_data=get_chart2_data(),
        result=last_result,
        history=get_history(),
        monitored_urls=get_monitored_urls(),
        url_graph_data=get_url_wise_data(),
        alerts=alerts_list   # 🔥 REAL-TIME ALERTS
    )


# ----------------------------
# ADD URL
# ----------------------------
@app.route('/add_url', methods=['POST'])
def add_url():
    url = request.form.get('monitor_url')

    if not url:
        return redirect('/dashboard')

    if not url.startswith("http"):
        url = "https://" + url

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO monitored_urls (url) VALUES (%s) ON CONFLICT DO NOTHING;",
        (url,)
    )

    conn.commit()
    cur.close()
    conn.close()

    return redirect('/dashboard')


# ----------------------------
# DELETE URL
# ----------------------------
@app.route('/delete_url/<path:url>')
def delete_url(url):
    url = unquote(url)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("DELETE FROM monitored_urls WHERE url=%s;", (url,))
    conn.commit()

    cur.close()
    conn.close()

    return redirect('/dashboard')


# ----------------------------
# CHECK URL
# ----------------------------
@app.route('/check', methods=['POST'])
def check_data():
    global last_result

    url = request.form.get('url')

    if not url:
        return redirect('/dashboard')

    if not url.startswith("http"):
        url = "https://" + url

    try:
        start = time.time()
        response = requests.get(url, timeout=5)
        response_time = time.time() - start

        status = "Success" if response.status_code == 200 else "Error"
        error_msg = "OK" if status == "Success" else str(response.status_code)
        score = 100 if status == "Success" else 50

        last_result = {
            "url": url,
            "status": status,
            "error": error_msg,
            "response_time": round(response_time, 2),
            "score": score
        }

        if status == "Error":
            send_email_alert("🚨 Alert", f"{url} failed")

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute("INSERT INTO posts (value, status) VALUES (%s, %s);",
                    (int(response_time * 100), status))

        cur.execute("""
            INSERT INTO history (url, status, response_time, score)
            VALUES (%s, %s, %s, %s);
        """, (url, status, response_time, score))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        last_result = {
            "url": url,
            "status": "Error",
            "error": str(e),
            "response_time": 0,
            "score": 0
        }

        send_email_alert("🚨 Error", str(e))

    return redirect('/dashboard')


# ----------------------------
# PDF REPORT
# ----------------------------
@app.route('/download_report')
def download_report():
    c = canvas.Canvas("report.pdf")
    c.drawString(100, 800, "Data Reliability Report")

    history = get_history()

    y = 750
    for row in history:
        c.drawString(100, y, str(row))
        y -= 20

    c.save()

    return "✅ Report Generated"


# ----------------------------
# SCHEDULER
# ----------------------------
scheduler = BackgroundScheduler()
scheduler.add_job(func=auto_check_urls, trigger="interval", seconds=60)
scheduler.start()


# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
