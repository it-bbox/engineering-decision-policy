#!/usr/bin/env python3
"""Build one standalone HTML from the maintained template and bundle sources."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    names = ["SKILL.md", "AGENTS.md", "CLAUDE.md", "README.md", "agents/openai.yaml"]
    for folder, pattern in (("configs", "*.json"), ("docs", "*.md"), ("scripts", "*.py"),
                            ("tests", "*.py"), ("demo/variants", "*.py")):
        names.extend(str(path.relative_to(ROOT)) for path in sorted((ROOT / folder).glob(pattern)))
    data = {
        "files": {name: (ROOT / name).read_text(encoding="utf-8") for name in names},
        "profiles": {name: json.loads((ROOT / f"configs/{name}.json").read_text(encoding="utf-8"))
                     for name in ("production", "mvp", "realtime")},
        "baseline": json.loads((ROOT / "demo/reports/testable.json").read_text(encoding="utf-8")),
        "efficient": json.loads((ROOT / "demo/reports/efficient.json").read_text(encoding="utf-8")),
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = (ROOT / "assets/page.html").read_text(encoding="utf-8")
    if template.count("__BUNDLE_DATA__") != 1:
        raise ValueError("Template must contain exactly one data placeholder")
    (ROOT / "index.html").write_text(template.replace("__BUNDLE_DATA__", payload), encoding="utf-8")
    print(f"Built index.html with {len(names)} embedded source files")


if __name__ == "__main__":
    main()
