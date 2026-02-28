#!/usr/bin/env python3
"""Gate 2: CloudFormation syntax validation via cfn-lint for IaCGen OpenClaw Skill.

Usage:
    python3 validate_cfn.py <template_path>

Exits 0 on pass (no errors), 1 on failure.
Prints JSON result to stdout.
"""
import sys
import json
import subprocess


def validate_cfn(template_path: str) -> dict:
    try:
        result = subprocess.run(
            ["cfn-lint", "-f", "json", template_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return {
            "passed": False,
            "error": "cfn-lint not found on PATH. Install with: pip install cfn-lint",
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "cfn-lint timed out after 60 seconds"}

    errors = []
    warnings = []
    informational = []

    if result.stdout.strip():
        try:
            matches = json.loads(result.stdout)
            for match in matches:
                level = match.get("Level", "Error")
                path_parts = match.get("Location", {}).get("Path", [])
                # Prefer the actual resource name (index 1 after 'Resources')
                resource = (
                    path_parts[1]
                    if len(path_parts) >= 2 and path_parts[0] == "Resources"
                    else (path_parts[-1] if path_parts else "Unknown")
                )
                entry = {
                    "resource": resource,
                    "message": match.get("Message", ""),
                    "line": match.get("Location", {}).get("Start", {}).get("LineNumber", 0),
                    "rule": match.get("Rule", {}).get("Id", ""),
                    "documentation": match.get("Rule", {}).get("Url", ""),
                }

                if level == "Error":
                    errors.append(entry)
                elif level == "Warning":
                    warnings.append(entry)
                else:
                    informational.append(entry)

        except (json.JSONDecodeError, TypeError):
            if result.returncode not in (0, 2):  # 2 = warnings only
                return {
                    "passed": False,
                    "error": f"cfn-lint parse error: {result.stderr or result.stdout[:500]}",
                }

    passed = len(errors) == 0
    return {
        "passed": passed,
        "total_issues": len(errors) + len(warnings) + len(informational),
        "severity_breakdown": {
            "error": len(errors),
            "warning": len(warnings),
            "informational": len(informational),
        },
        "error_details": errors,
        "warning_details": warnings,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"passed": False, "error": "Usage: validate_cfn.py <template_path>"}))
        sys.exit(1)

    result = validate_cfn(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
