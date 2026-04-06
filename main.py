from ingestion.fetch_data import fetch_data
from storage.db import create_table, insert_data
from processing.validator import validate_data
from processing.anomaly import detect_anomaly
from alerts.alert import send_alert

def run_pipeline():
    print("🚀 Pipeline Started...")

    data = fetch_data()

    if not data:
        send_alert("No data fetched!")
        return

    # Create table
    create_table()

    # Insert data
    insert_data(data)

    # Validate data
    errors = validate_data(data)
    if errors:
        for error in errors:
            send_alert(error)

    # Detect anomaly
    anomaly = detect_anomaly(data)
    if anomaly:
        send_alert(anomaly)

    print("✅ Pipeline Completed Successfully")


if __name__ == "__main__":
    run_pipeline()
