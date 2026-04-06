def validate_data(data):
    errors = []

    for record in data:
        if not record.get("title"):
            errors.append(f"Missing title in ID {record.get('id')}")

        if not record.get("body"):
            errors.append(f"Missing body in ID {record.get('id')}")

    return errors
