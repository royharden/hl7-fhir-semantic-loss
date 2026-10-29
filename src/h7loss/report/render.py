"""Render supplied records as inert HTML without certifying their claims."""

import html
import json
from collections.abc import Mapping


def render_report(report: dict) -> str:
    """Escape every supplied field, including strings resembling markup or links.

    Imported records remain unverified inputs. This renderer never computes an
    evaluation headline or upgrades a supplied receipt into a measured result.
    """
    if not isinstance(report, Mapping):
        raise ValueError("report must be a JSON object")
    payload = json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False)
    escaped = html.escape(payload, quote=True)
    record = report.get("record", report)
    if not isinstance(record, Mapping):
        raise ValueError("supplied record must be an object")
    result = record.get("result", record)
    if not isinstance(result, Mapping):
        result = {}
    rows = []
    # Display literal producer states, never infer Java/semantic success from them.
    for name in ("case_id", "arm_id", "outcome", "raw_sha256", "dictionary_sha256", "error"):
        if name in result:
            value = json.dumps(result[name], ensure_ascii=True, allow_nan=False)
            rows.append('<tr><th scope="row">' + html.escape(name) + '</th><td><code>'
                        + html.escape(value, quote=True) + '</code></td></tr>')
    sections = []
    for name in ("validation", "roundtrip", "ledger", "dispositions", "attempts", "failures"):
        owner = record if name in record else result
        if name in owner:
            value = json.dumps(owner[name], ensure_ascii=True, indent=2, allow_nan=False)
            sections.append('<h2>Supplied ' + name + ' (unverified)</h2><pre>'
                            + html.escape(value, quote=True) + '</pre>')
    summary = '<h2>Supplied producer state (unverified)</h2><table>' + ''.join(rows) + '</table>' if rows else ''
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>Semantic Loss Lab — construction report</title></head><body>'
        '<h1>Semantic Loss Lab</h1>'
        '<p>Construction artifact — runtime unverified. Supplied records below '
        'are unverified inputs, not measured or independently accepted results.</p>'
        '<p>No clinical claim. Rights, independent truth, fidelity, actual Java '
        'validation, custody seals and release approval remain separate gates.</p>'
        + summary + ''.join(sections)
        + '<h2>Complete supplied record</h2><pre>' + escaped + '</pre></body></html>\n'
    )
