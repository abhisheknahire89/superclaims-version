"""The OpenAPI document (pack/api/openapi.yaml) drives request validation and required-header checks, so the running
service cannot silently drift from the published contract."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


class Contract:
    def __init__(self, pack_dir: Path):
        self.doc = yaml.safe_load((pack_dir / "api" / "openapi.yaml").read_text(encoding="utf-8"))
        schemas_dir = pack_dir / "schemas"
        resources = [("urn:aw:openapi", Resource.from_contents({**self._rewrite(self.doc), "$schema": "https://json-schema.org/draft/2020-12/schema"}))]
        for p in schemas_dir.glob("*.json"):
            resources.append((f"urn:aw:schemas:{p.name}", Resource.from_contents(json.loads(p.read_text(encoding="utf-8")))))
        self.registry = Registry().with_resources(resources)
        self.ops: dict[str, dict] = {}
        for path, item in self.doc["paths"].items():
            for method, op in item.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                params = [self._deref(p) for p in item.get("parameters", []) + op.get("parameters", [])]
                body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
                self.ops[op["operationId"]] = {
                    "method": method.upper(), "path": path,
                    "required_headers": [p["name"] for p in params if p.get("in") == "header" and p.get("required")],
                    "validator": Draft202012Validator(self._rewrite(body), registry=self.registry) if body else None,
                }

    @staticmethod
    def _rewrite(obj):
        """Point '#/components/…' refs at the registered OpenAPI resource and '../schemas/x.json' at the schema resources."""
        obj = copy.deepcopy(obj)

        def walk(o):
            if isinstance(o, dict):
                for k, v in list(o.items()):
                    if k == "$ref" and isinstance(v, str):
                        if v.startswith("#/"):
                            o[k] = "urn:aw:openapi" + v
                        elif v.startswith("../schemas/"):
                            o[k] = "urn:aw:schemas:" + v.split("/")[-1]
                    else:
                        walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(obj)
        return obj

    def _deref(self, p: dict) -> dict:
        if "$ref" in p:
            node = self.doc
            for part in p["$ref"].lstrip("#/").split("/"):
                node = node[part]
            return node
        return p

    def validate(self, operation_id: str, body) -> list[dict]:
        v = self.ops[operation_id]["validator"]
        if v is None:
            return []
        return [{"pointer": "/" + "/".join(map(str, e.path)), "message": e.message} for e in v.iter_errors(body)]

    def required_headers(self, operation_id: str) -> list[str]:
        return self.ops[operation_id]["required_headers"]

    def response_validator(self, ref: str) -> Draft202012Validator:
        return Draft202012Validator({"$ref": re.sub(r"^\.\./schemas/", "urn:aw:schemas:", ref)}, registry=self.registry)
