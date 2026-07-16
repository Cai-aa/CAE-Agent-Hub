from __future__ import annotations

import re


_BLOCKED_TCL = (
    (re.compile(r"(^|[;\n\[])\s*exec\b", re.IGNORECASE), "exec"),
    (re.compile(r"(^|[;\n\[])\s*socket\b", re.IGNORECASE), "socket"),
    (re.compile(r"(^|[;\n\[])\s*load\b", re.IGNORECASE), "load"),
    (re.compile(r"(^|[;\n\[])\s*open\b", re.IGNORECASE), "open"),
    (re.compile(r"(^|[;\n\[])\s*file\b", re.IGNORECASE), "file"),
    (re.compile(r"(^|[;\n\[])\s*(cd|pwd|glob)\b", re.IGNORECASE), "filesystem navigation"),
    (re.compile(r"(^|[;\n\[])\s*(package|interp)\b", re.IGNORECASE), "dynamic Tcl runtime"),
    (re.compile(r"(^|[;\n\[])\s*exit\b", re.IGNORECASE), "exit"),
    (re.compile(r"(^|[;\n])\s*source\b", re.IGNORECASE), "source"),
    (re.compile(r"(^|[;\n])\s*\*quit\b", re.IGNORECASE), "*quit"),
    (re.compile(r"(?i)(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]"), "absolute Windows path"),
    (re.compile(r"(?:^|[\s\"'{])\\\\"), "UNC path"),
    (re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)"), "parent path traversal"),
    (re.compile(r"(?i)(?:\$|::)env(?:\(|\b)"), "environment access"),
)


def validate_tcl(content: str) -> dict:
    """Reject OS/process escape commands; HyperMesh commands remain available."""
    if not content.strip():
        raise ValueError("Tcl content must not be empty")
    if "\x00" in content:
        raise ValueError("Tcl content contains a NUL byte")
    if len(content.encode("utf-8")) > 2_000_000:
        raise ValueError("Tcl content exceeds the 2 MB safety limit")
    blocked = [label for pattern, label in _BLOCKED_TCL if pattern.search(content)]
    if blocked:
        raise ValueError(
            "Tcl content contains blocked commands: " + ", ".join(sorted(set(blocked)))
        )
    return {
        "valid": True,
        "line_count": len(content.splitlines()),
        "blocked_commands": [],
    }
