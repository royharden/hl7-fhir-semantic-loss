"""Deterministic, authored synthetic developer messages using local vocabularies.

This module creates source inputs only. It supplies no expected FHIR output,
semantic assertions, admission decision, independent review, or measured result.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from typing import Any

SITES = tuple(f"dev-{number:02d}" for number in range(1, 9))
CASES_PER_SITE = 50
SCORED_PER_SITE = 45


def _site_number(site_id: str) -> int:
    if site_id not in SITES:
        raise ValueError("developer site_id must be dev-01 through dev-08")
    return int(site_id[-2:])


def _canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def development_dictionary(site_id: str = "dev-01") -> dict[str, Any]:
    """Return fresh original local-code metadata, with admission explicitly pending."""
    site = _site_number(site_id)
    system = f"urn:h7loss:dev:{site_id}:observation"
    codes = {}
    for kind, display in (
        ("NM", "Synthetic numeric signal"),
        ("SN", "Synthetic structured signal"),
        ("ST", "Synthetic text signal"),
        ("CWE", "Synthetic categorical signal"),
    ):
        code = f"D{site:02d}{kind}"
        codes[code] = {"system": system, "code": code, "display": display}
    dictionary = {
        "site_id": site_id,
        "dictionary_id": f"h7loss-{site_id}-authored-v1",
        "provenance": {
            "kind": "original_developer_authored",
            "admission": "NOT_ADMITTED",
            "rights_review": "PENDING",
            "independent_semantic_review": "PENDING",
            "purpose": "synthetic developer input only; not clinical terminology",
        },
        "codes": {**codes, "DEVPANEL": {
            "system": f"urn:h7loss:dev:{site_id}:panel",
            "code": "DEVPANEL", "display": "Synthetic developer panel",
        }},
        "identifier_systems": {"H7LOSSDEV": "urn:h7loss:dev:patient-id"},
        "observation_statuses": {"F": "final", "P": "preliminary"},
        "report_statuses": {"F": "final", "P": "preliminary"},
        "coding_authorities": {"LOCAL": [
            system, f"urn:h7loss:dev:{site_id}:panel",
            f"urn:h7loss:dev:{site_id}:category", "urn:h7loss:dev:units",
        ]},
        "time_fields": {"OBR.7": "report_effective", "OBX.14": "observation_effective"},
        "note_scopes": {"NTE.3": ["order", "observation"]},
        "flags": {token: {"system": "urn:h7loss:dev:flags", "code": token,
                          "display": display} for token, display in (
                              ("A", "Authored synthetic abnormal"), ("H", "Authored synthetic high"))},
        "units": {
            "du": {
                "system": "urn:h7loss:dev:units",
                "code": "du",
                "display": "Synthetic developer unit",
            }
        },
        "value_codes": {
            "BLUE": {
                "system": f"urn:h7loss:dev:{site_id}:category",
                "code": "BLUE",
                "display": "Synthetic blue category",
            },
            "AMBER": {
                "system": f"urn:h7loss:dev:{site_id}:category",
                "code": "AMBER",
                "display": "Synthetic amber category",
            },
        },
        "z_segments": {},
    }
    # Consumer views are derived from the original maps, never authored twice.
    dictionary["tables"] = {
        "observation_codes": {key: value["code"] for key, value in codes.items()},
        "observation_systems": {key: value["system"] for key, value in codes.items()},
        "units": {key: value["code"] for key, value in dictionary["units"].items()},
        "observation_statuses": dict(dictionary["observation_statuses"]),
        "report_statuses": dict(dictionary["report_statuses"]),
        "flags": {key: value["code"] for key, value in dictionary["flags"].items()},
    }
    dictionary["bindings"] = {}
    dictionary["report_code"] = dictionary["codes"]["DEVPANEL"]["display"]
    return dictionary


def _segment(tag: str, fields: dict[int, str]) -> str:
    if not re.fullmatch(r"[A-Z0-9]{3}", tag):
        raise ValueError("invalid developer segment tag")
    maximum = max(fields, default=0)
    return tag + "|" + "|".join(fields.get(number, "") for number in range(1, maximum + 1))


def _value(kind: str, index: int, observation: int) -> str:
    if kind == "NM":
        return ("5.00", "-0.20", "100.125")[index % 3]
    if kind == "SN":
        return (">^5.00", "^2^:^3", "^1^-^4")[index % 3]
    if kind == "ST":
        return (
            r"literal\F\pipe\S\component\T\sub\R\repeat\E\escape",
            "first\\.br\\second\\X3C\\tag\\X3E\\",
            '""',
            r"alpha~beta\F\gamma",
        )[(index + observation) % 4]
    return ("BLUE^Synthetic blue category^LOCAL", "AMBER^Synthetic amber category^LOCAL")[
        index % 2
    ]


def generate_case(site_id: str = "dev-01", index: int = 0) -> dict[str, Any]:
    """Build one deterministic developer case, without writing or executing anything.

    Indices 0..44 are intended developer scored inputs; 45..49 are separately
    marked onboarding inputs. These are planned roles, not evaluation results.
    Bytes are ASCII and use CR or CRLF, with one patient, one/two orders and
    one/two/three observations per order. Unknown Z content has no released meaning.
    """
    site = _site_number(site_id)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < CASES_PER_SITE:
        raise ValueError("developer index must be an integer from 0 through 49")
    dictionary = development_dictionary(site_id)
    case_id = f"{site_id}-{index:03d}"
    patient_id = f"SYNTH-{site:02d}-{index:03d}"
    segments = [
        "MSH|^~\\&|H7LOSS-DEV|" + site_id
        + "|LOCAL|LOCAL|20260102120000+0000||ORU^R01|" + case_id + "|P|2.8",
        _segment("PID", {1: "1", 3: patient_id + "^^^H7LOSSDEV", 5: "Synthetic^Developer", 8: ("U", "O")[index % 2]}),
    ]
    for order in range(1 + index % 2):
        order_id = f"{case_id}-O{order + 1}"
        segments.extend([
            _segment("ORC", {1: "RE", 2: order_id}),
            _segment("OBR", {1: str(order + 1), 2: order_id, 4: "DEVPANEL^Synthetic panel^LOCAL", 7: "20260102120000+0000", 25: ("F", "P")[index % 2]}),
            _segment("NTE", {1: "1", 3: "Original synthetic order note"}),
        ])
        for observation in range(1 + (index + order) % 3):
            kind = ("NM", "SN", "ST", "CWE")[(index + order + observation) % 4]
            code = f"D{site:02d}{kind}"
            value = _value(kind, index, observation)
            segments.extend([
                _segment("OBX", {
                    1: str(observation + 1), 2: kind,
                    3: code + "^" + dictionary["codes"][code]["display"] + "^LOCAL",
                    4: str(observation + 1), 5: value,
                    6: "du^Synthetic developer unit^LOCAL" if kind in {"NM", "SN"} else "",
                    8: ("", "A", "H")[index % 3], 11: ("F", "P")[index % 2],
                    14: "20260102120000" if index % 5 == 0 else "20260102120000+0000",
                }),
                _segment("NTE", {1: "1", 3: "Original synthetic observation note " + str(observation + 1)}),
            ])
        segments.append(_segment("ZDV", {1: f"unreleased-{site_id}-{order + 1}", 2: "opaque~distinct"}))
    separator = "\r\n" if site % 2 == 0 else "\r"
    raw = (separator.join(segments) + separator).encode("ascii")
    return {
        "case_id": case_id,
        "site_id": site_id,
        "index": index,
        "partition": "development",
        "usage": "onboarding" if index >= SCORED_PER_SITE else "developer_scored_input",
        "provenance": {
            "kind": "original_developer_authored",
            "admission": "NOT_ADMITTED",
            "independent_review": "PENDING",
            "measured": False,
        },
        "raw": raw,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "dictionary": dictionary,
        "dictionary_sha256": _canonical_hash(dictionary),
    }


def generate_development_cases() -> Iterator[dict[str, Any]]:
    """Yield the bounded 8x50 developer input design; never held-out material."""
    for site_id in SITES:
        for index in range(CASES_PER_SITE):
            yield generate_case(site_id, index)
