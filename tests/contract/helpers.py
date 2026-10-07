"""Shared contract helpers. Also a tiny CLI used by scripts/ci/run_schemathesis.sh:

python -m tests.contract.helpers implemented RatelLink   # operationIds to fuzz, one per line
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "openapi.yaml"
NOT_IMPLEMENTED = ROOT / "contracts" / "not_implemented.txt"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@dataclass(frozen=True)
class Op:
    op_id: str
    method: str
    path: str
    tag: str
    raw: dict[str, Any]


def load_contract() -> dict[str, Any]:
    data = yaml.safe_load(CONTRACT.read_text())
    assert isinstance(data, dict)
    return data


def operations(spec: dict[str, Any] | None = None) -> list[Op]:
    spec = spec or load_contract()
    ops: list[Op] = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method in HTTP_METHODS:
                ops.append(Op(op["operationId"], method.upper(), path, op["tags"][0], op))
    return ops


def not_implemented() -> set[str]:
    lines = (ln.strip() for ln in NOT_IMPLEMENTED.read_text().splitlines())
    return {ln for ln in lines if ln and not ln.startswith("#")}


def implemented_ids(tag: str) -> list[str]:
    skip = not_implemented()
    return [o.op_id for o in operations() if o.tag == tag and o.op_id not in skip]


def resolve(spec: dict[str, Any], node: Any) -> Any:
    """Follow local $ref pointers."""
    while isinstance(node, dict) and "$ref" in node:
        target: Any = spec
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "implemented":
        sys.stdout.write("\n".join(implemented_ids(sys.argv[2])) + "\n")
    else:
        sys.stderr.write("usage: python -m tests.contract.helpers implemented <Tag>\n")
        sys.exit(2)
