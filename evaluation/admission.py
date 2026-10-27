"""Conservative actual-use admission. Structural completeness is not rights clearance."""
from .common import Refusal, digest, require_hash

REQUIRED_GATES = {"G1", "G2", "G3", "G4", "G5", "G6", "G7"}

def inspect_dossier(dossier):
    issues = []
    assets = dossier.get("assets", [])
    if not assets:
        issues.append("asset inventory missing")
    ids = set()
    for asset in assets:
        identity = asset.get("id")
        if not identity or identity in ids:
            issues.append("asset id missing/duplicate")
        ids.add(identity)
        for key in ("source_url", "edition", "path", "owner", "license_expression", "license_text_sha256", "use_mode", "reviewer", "reason"):
            if not asset.get(key):
                issues.append(f"{identity}: missing {key}")
        for key in ("sha256", "license_text_sha256"):
            try:
                require_hash(asset.get(key))
            except Refusal:
                issues.append(f"{identity}: unresolved {key}")
        if asset.get("decision") != "CLEARED":
            issues.append(f"{identity}: rights unresolved")
    gates = dossier.get("gates", {})
    for gate in sorted(REQUIRED_GATES):
        if gates.get(gate) != "GO":
            issues.append(f"{gate}: not GO")
    # Signatures are supplied by Roy-appointed custodians, never generated here.
    for role in ("H", "Q"):
        receipt = dossier.get("approvals", {}).get(role, {})
        if not receipt.get("actor") or receipt.get("manifest_sha256") != digest(assets) or receipt.get("decision") != "GO":
            issues.append(f"{role}: missing manifest-bound approval")
    return {"status": "NOT_ADMITTED" if issues else "STRUCTURALLY_COMPLETE", "issues": issues,
            "manifest_sha256": digest(assets), "rights_verified": False,
            "note": "External role identity/signature and actual rights verification required; this tool cannot issue GO."}

def require_admission(dossier):
    result = inspect_dossier(dossier)
    if result["issues"]:
        raise Refusal("admission unresolved: " + "; ".join(result["issues"]))
    raise Refusal("structural dossier alone cannot authorize execution; external admission verification required")
