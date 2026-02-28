#!/usr/bin/env python3
"""Gate 1: YAML format validation for IaCGen OpenClaw Skill.

Usage:
    python3 validate_yaml.py <template_path>

Exits 0 on pass, 1 on failure.
Prints JSON result to stdout.
"""
import sys
import json

try:
    from yamllint import linter
    from yamllint.config import YamlLintConfig
except ImportError:
    print(json.dumps({
        "passed": False,
        "error": "yamllint not installed. Run: pip install yamllint"
    }))
    sys.exit(1)

# Relaxed config matching IaCGen's original yamllint settings
RELAXED_CONFIG = YamlLintConfig("""
extends: relaxed
rules:
  line-length: disable
  trailing-spaces: disable
  new-line-at-end-of-file: disable
  empty-lines:
    max: 3
    max-start: 0
    max-end: 0
  indentation:
    spaces: consistent
    indent-sequences: true
    check-multi-line-strings: false
""")


def validate_yaml(template_path: str) -> dict:
    try:
        with open(template_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        return {"passed": False, "error": f"File not found: {template_path}"}
    except IOError as e:
        return {"passed": False, "error": f"Cannot read file: {e}"}

    problems = list(linter.run(content, RELAXED_CONFIG))
    errors = [p for p in problems if p.level == "error"]

    if not errors:
        return {"passed": True, "error": None, "warnings": len(problems) - len(errors)}

    details = [f"Line {p.line}: {p.message} (rule: {p.rule})" for p in errors]
    return {
        "passed": False,
        "error": details[0],
        "error_count": len(errors),
        "details": details,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"passed": False, "error": "Usage: validate_yaml.py <template_path>"}))
        sys.exit(1)

    result = validate_yaml(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
