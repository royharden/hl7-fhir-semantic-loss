"""Builder-authored developer cases; never independent gold or held-out data."""

import hashlib
import json

import pytest

from h7loss.gen.development import development_dictionary


def _segment(tag, fields):
    return tag + "|" + "|".join(fields.get(number, "") for number in range(1, max(fields) + 1))


@pytest.fixture
def dsl_case():
    """Return a small literal-input builder case with explicit mapping proposals.

    The producer dictionary is exercised as a real public consumer seam. Assertions
    in callers remain builder unit expectations, not independently verified meaning.
    """
    def make(datatype="ST", value="alpha", *, unit=False, tail="", timestamp=None):
        dictionary = development_dictionary("dev-01")
        segments = [
            "MSH|^~\\&|UNIT|UNIT|LOCAL|LOCAL|20260102120000+0000||ORU^R01|UNIT-1|P|2.8",
            _segment("PID", {1: "1", 3: "TESTUNIT-1^^^H7LOSSDEV"}),
            _segment("OBR", {1: "1", 4: "DEVPANEL^Synthetic developer panel^LOCAL", 25: "F"}),
            _segment("OBX", {1: "1", 2: datatype,
                3: "D01" + datatype + "^Synthetic unit code^LOCAL", 5: value,
                6: "du^Synthetic developer unit^LOCAL" if unit else "", 11: "F",
                **({14: timestamp} if timestamp is not None else {})}),
        ]
        if tail:
            segments.extend(tail.split("\r"))
        raw = ("\r".join(segments) + "\r").encode("ascii")

        def rule(segment, scope, field, target, transform="copy_text", *, component=1,
                 repetition=1, table=None):
            item = {"source": {"segment": segment, "scope": scope, "field": field,
                    "repetition": repetition, "component": component, "subcomponent": 1},
                    "target": target, "transform": transform}
            if table is not None:
                item["dictionary"] = table
            return item

        rules = [
            rule("PID", "patient", 3, "patient.id"),
            rule("PID", "patient", 3, "patient.system", "dictionary_lookup", component=4, table="identifier_systems"),
            rule("OBR", "order", 25, "report.status", "dictionary_lookup", table="report_statuses"),
            rule("OBX", "observation", 3, "observation.code", "dictionary_lookup", table="codes"),
            rule("OBX", "observation", 11, "observation.status", "dictionary_lookup", table="observation_statuses"),
            rule("OBX", "observation", 5, "observation.value", "repeated_value",
                 component="all" if datatype in {"SN", "CWE"} else 1, repetition="all"),
        ]
        if unit:
            rules.append(rule("OBX", "observation", 6, "observation.unit", "unit_from_dictionary", table="units"))
        if timestamp is not None:
            rules.append(rule("OBX", "observation", 14, "observation.time", "timestamp_preserve_precision"))

        def proposal():
            return {"version": 1, "site_id": "dev-01", "dictionary_sha256": hashlib.sha256(
                json.dumps(dictionary, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                           allow_nan=False).encode()).hexdigest(), "rules": rules}

        return raw, dictionary, rules, rule, proposal
    return make
