"""Deterministic JSON/hash helpers; no implicit file discovery."""
import hashlib
import json
import re

class Refusal(ValueError):
    """Missing, malformed or drifted evidence: caller must stop."""

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def require_hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise Refusal("expected lowercase SHA256")
    return value

def pointer(document, path):
    if path == "":
        return document
    if not isinstance(path, str) or not path.startswith("/"):
        raise Refusal("only local JSON pointers supported")
    node = document
    for part in path[1:].split("/"):
        if re.search(r"~(?![01])", part):
            raise Refusal("invalid pointer escape")
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", part):
                raise Refusal("invalid array index")
            node = node[int(part)]
        elif isinstance(node, dict):
            node = node[part]
        else:
            raise Refusal("pointer traverses scalar")
    return node
