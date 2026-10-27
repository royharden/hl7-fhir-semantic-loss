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
        '<h2>Supplied record</h2><pre>' + escaped + '</pre></body></html>\n'
    )
