"""Load the Hibiscus server contract snapshot and validate requests / responses against it (JSON Schema 2020-12).

Vendored from the Hibiscus repository (``cli/tests/openapi_contract.py`` at tag v0.1.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SPEC_PATH = Path(__file__).resolve().parent / "contract" / "hibiscus-v0.1.1" / "openapi.yaml"
SPEC_URI = "https://hibiscus.test/openapi.json"
METHODS = ("get", "put", "post", "delete", "patch")


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


@dataclass(frozen=True)
class Operation:
    method: str
    template: str
    operation_id: str
    pointer: str  # JSON pointer of the operation object
    regex: re.Pattern[str]
    param_names: tuple[str, ...]


class ContractError(AssertionError):
    pass


class OpenApiContract:
    def __init__(self, path: Path = SPEC_PATH) -> None:
        self.spec: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        resource: Resource[Any] = DRAFT202012.create_resource(self.spec)
        self.registry: Registry[Any] = Registry().with_resource(SPEC_URI, resource)
        self._validators: dict[str, Draft202012Validator] = {}

    @cached_property
    def operations(self) -> list[Operation]:
        ops: list[Operation] = []
        for template, item in self.spec["paths"].items():
            names = tuple(re.findall(r"{([^}]+)}", template))
            # `{path}` in /files/{path} is URL-encoded (one segment); others are single segments too
            rx = (
                "^"
                + re.sub(r"{[^}]+}", r"([^/]+)", re.escape(template).replace(r"\{", "{").replace(r"\}", "}"))
                + "$"
            )
            for method in METHODS:
                if method in item:
                    ops.append(
                        Operation(
                            method=method.upper(),
                            template=template,
                            operation_id=item[method]["operationId"],
                            pointer=f"/paths/{_escape(template)}/{method}",
                            regex=re.compile(rx),
                            param_names=names,
                        )
                    )
        # literal segments must win over templated ones (/runs/preflight vs /runs/{run_id})
        ops.sort(key=lambda o: (o.template.count("{"), -len(o.template)))
        return ops

    def match(self, method: str, path: str) -> tuple[Operation, dict[str, str]]:
        for op in self.operations:
            if op.method != method:
                continue
            m = op.regex.match(path)
            if m:
                return op, dict(zip(op.param_names, m.groups(), strict=True))
        raise ContractError(f"{method} {path} is not an operation in the Hibiscus v0.1.1 contract")

    def resolve(self, pointer: str) -> Any:
        node: Any = self.spec
        for raw in pointer.strip("/").split("/"):
            key = raw.replace("~1", "/").replace("~0", "~")
            node = node[int(key)] if isinstance(node, list) else node[key]
        return node

    def _follow_ref(self, pointer: str) -> str:
        node = self.resolve(pointer)
        while isinstance(node, dict) and "$ref" in node and len(node) == 1:
            ref = node["$ref"]
            if not ref.startswith("#"):
                raise ContractError(f"external ref {ref}")
            pointer = ref[1:]
            node = self.resolve(pointer)
        return pointer

    def validator(self, pointer: str) -> Draft202012Validator:
        v = self._validators.get(pointer)
        if v is None:
            v = Draft202012Validator({"$ref": f"{SPEC_URI}#{pointer}"}, registry=self.registry)
            self._validators[pointer] = v
        return v

    def validate(self, pointer: str, instance: Any, what: str) -> None:
        errors = sorted(self.validator(pointer).iter_errors(instance), key=lambda e: list(e.path))
        if errors:
            msgs = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
            raise ContractError(f"{what} violates {pointer}: {msgs}")

    def schema_pointer(self, name: str) -> str:
        return f"/components/schemas/{name}"

    def request_body_pointer(self, op: Operation, content_type: str) -> str | None:
        node = self.resolve(op.pointer)
        if "requestBody" not in node:
            return None
        rb = self._follow_ref(f"{op.pointer}/requestBody")
        content = self.resolve(rb).get("content", {})
        if content_type not in content:
            raise ContractError(
                f"{op.operation_id}: request content-type {content_type} not in {list(content)}"
            )
        return f"{rb}/content/{_escape(content_type)}/schema"

    def response_pointer(self, op: Operation, status: int, content_type: str) -> str | None:
        responses = self.resolve(op.pointer)["responses"]
        key = str(status)
        if key not in responses:
            raise ContractError(f"{op.operation_id}: status {status} not documented ({sorted(responses)})")
        rp = self._follow_ref(f"{op.pointer}/responses/{key}")
        content = self.resolve(rp).get("content")
        if not content:
            return None
        if content_type not in content:
            raise ContractError(
                f"{op.operation_id} {status}: content-type {content_type} not in {list(content)}"
            )
        return f"{rp}/content/{_escape(content_type)}/schema"

    def header_params(self, op: Operation) -> list[dict[str, Any]]:
        params: list[dict[str, Any]] = []
        path_item = self.resolve(op.pointer.rsplit("/", 1)[0])
        for p in [*path_item.get("parameters", []), *self.resolve(op.pointer).get("parameters", [])]:
            if "$ref" in p:
                p = self.resolve(p["$ref"][1:])
            if p.get("in") == "header":
                params.append(p)
        return params
