"""Strict, bounded request parser; runs in the existing isolated Python image."""
import json
import re
import sys

FILES = (
    "login_service.py", "site_sessions.py", "init_login.py", "worker.py",
    "gallery_engine.py", "sources.py", "requirements-worker.txt",
)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def parse(raw):
    if len(raw) > 4096:
        raise ValueError("oversized request")
    request = json.loads(raw, object_pairs_hook=unique)
    if type(request) is not dict or set(request) != {
        "schema", "enabled", "generation", "revision", "worker", "files"
    }:
        raise ValueError("request fields")
    if type(request["schema"]) is not int or request["schema"] != 1:
        raise ValueError("schema")
    for name in ("enabled", "worker"):
        if type(request[name]) is not bool:
            raise ValueError("boolean")
    if type(request["generation"]) is not int or not 1 <= request["generation"] <= 2147483647:
        raise ValueError("generation")
    if not isinstance(request["revision"], str) or not re.fullmatch("[0-9a-f]{40}", request["revision"]):
        raise ValueError("revision")
    files = request["files"]
    if type(files) is not dict or set(files) != set(FILES):
        raise ValueError("source allowlist")
    for digest in files.values():
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("digest")
    return request


if __name__ == "__main__":
    try:
        r = parse(sys.stdin.buffer.read(4097))
        print("enabled" if r["enabled"] else "disabled")
        print(r["generation"])
        print(r["revision"])
        print("yes" if r["worker"] else "no")
        for name in FILES:
            print(r["files"][name] + "  studio/" + name)
    except (ValueError, TypeError):
        sys.exit("service_request=invalid")
