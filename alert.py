from datetime import datetime

def send_alert(message):
    with open("logs/alerts.log", "a") as f:
        f.write(f"{datetime.now()} - ALERT: {message}\n")

    print(f"ALERT: {message}")
