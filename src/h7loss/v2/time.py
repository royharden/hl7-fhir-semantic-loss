"""Original conservative compact timestamp conversion, no timezone invention."""

import re
from datetime import datetime


def timestamp_to_fhir(text: str) -> tuple[str, int]:
    match = re.fullmatch(r"(\d{4})(\d{2})?(\d{2})?(?:(\d{2})(\d{2})(\d{2})(\.\d{1,9})?([+-]\d{4}))?", text)
    if match is None:
        raise ValueError("unsupported_timestamp_precision_or_zone")
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    if hour is not None and (month is None or day is None):
        raise ValueError("incomplete_timestamp_date")
    datetime(int(year), int(month or 1), int(day or 1), int(hour or 0), int(minute or 0), int(second or 0))
    rendered = year + ("-" + month if month else "") + ("-" + day if day else "")
    precision = len(year + (month or "") + (day or ""))
    if hour is not None:
        offset_hour, offset_minute = int(zone[1:3]), int(zone[3:5])
        if offset_hour > 14 or offset_minute > 59 or (offset_hour == 14 and offset_minute):
            raise ValueError("unsupported_timestamp_offset")
        rendered += f"T{hour}:{minute}:{second}{fraction or ''}{zone[:3]}:{zone[3:]}"
        precision = 14 + (len(fraction) - 1 if fraction else 0)
    return rendered, precision
