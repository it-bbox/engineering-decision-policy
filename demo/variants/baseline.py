def export_rows(rows, emit, formatter=str):
    if any(not isinstance(row, str) for row in rows):
        raise ValueError("rows must contain strings")
    print("export")
    result = tuple(formatter(row) for row in rows)
    for row in rows:
        emit(formatter(row))
    return result
