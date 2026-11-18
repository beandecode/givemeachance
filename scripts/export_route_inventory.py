"""Export registered route declarations without loading private settings or a DB.

Usage: python scripts/export_route_inventory.py [--check]
The integration contract test also compares this inventory to Flask's live URL map.
"""

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "route-inventory.json"


def inventory():
    routes = []
    for path in sorted((ROOT / "app" / "route_groups").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "api_route"
                ):
                    routes.append(
                        {
                            "method": ast.literal_eval(decorator.args[1]),
                            "path": ast.literal_eval(decorator.args[2]),
                            "endpoint": node.name,
                            "module": str(path.relative_to(ROOT)),
                        }
                    )
                    continue
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "app":
                    continue
                if decorator.func.attr not in {"get", "post", "put", "patch", "delete"}:
                    continue
                routes.append(
                    {
                        "method": decorator.func.attr.upper(),
                        "path": ast.literal_eval(decorator.args[0]),
                        "endpoint": node.name,
                        "module": str(path.relative_to(ROOT)),
                    }
                )
    return sorted(routes, key=lambda row: (row["path"], row["method"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = json.dumps(inventory(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != expected:
            raise SystemExit("Route inventory is stale; run scripts/export_route_inventory.py")
        print("Route inventory is current")
    else:
        OUTPUT.write_text(expected)
        print(f"Exported {len(inventory())} routes to {OUTPUT.relative_to(ROOT)}")
