"""Validate JSON Schemas, configs, fixtures and the OpenAPI document (no network, stdlib + jsonschema + PyYAML).

Usage: python3 verification/validate_contracts.py
Checks:
  C1  every schema in schemas/ is a valid Draft 2020-12 schema
  C2  config/policy-*.json validates against policy-config.schema.json
  C3  every fixtures/claims/*.output.json validates against evaluation-result.schema.json
  C4  fixtures/extraction/*.json validates against extraction-output.schema.json (ignoring _test_note)
  C5  openapi.yaml parses, operationIds are unique, every operation declares responses,
      every $ref resolves (internal and relative-file)
  C6  every request-body example in openapi.yaml validates against its schema
  C7  enum parity: workflow / claim status / document status values agree between OpenAPI and db/schema.sql
"""
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
fails, passes = [], []


def ok(cond, label):
    (passes if cond else fails).append(label)


schemas = {p.name: json.loads(p.read_text()) for p in (ROOT / "schemas").glob("*.json")}
for name, s in schemas.items():
    try:
        Draft202012Validator.check_schema(s)
        ok(True, f"C1 {name}")
    except Exception as e:  # noqa: BLE001
        ok(False, f"C1 {name}: {e}")


def errors(schema, instance, registry=None):
    v = Draft202012Validator(schema, registry=registry) if registry else Draft202012Validator(schema)
    return [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]


CONFIG_SCHEMAS = {"policy-": "policy-config.schema.json", "tariff-": "tariff.schema.json", "nme-list-": "nme-list.schema.json",
                  "checklist-": "checklist.schema.json", "workflow-": "workflow-config.schema.json",
                  "classifier-map-": "classifier-map.schema.json"}
for p in sorted((ROOT / "config").glob("*.json")):
    sch = next(v for k, v in CONFIG_SCHEMAS.items() if p.name.startswith(k))
    e = errors(schemas[sch], json.loads(p.read_text()))
    ok(not e, f"C2 {p.name} vs {sch}" + (f": {e[:3]}" if e else ""))

for p in sorted((ROOT / "fixtures/claims").glob("*.input.json")):
    e = errors(schemas["engine-input.schema.json"], json.loads(p.read_text()))
    ok(not e, f"C2b {p.name} vs engine-input" + (f": {e[:3]}" if e else ""))

for p in sorted((ROOT / "fixtures/claims").glob("*.audit.json")):
    evs = json.loads(p.read_text())
    bad = [f"seq {ev.get('seq')}: {m}" for ev in evs for m in errors(schemas["audit-event.schema.json"], ev)]
    ok(not bad, f"C2c {p.name} vs audit-event ({len(evs)} events)" + (f": {bad[:3]}" if bad else ""))

for p in sorted((ROOT / "fixtures/worksheets").glob("*.json")):
    e = errors(schemas["settlement-worksheet.schema.json"], json.loads(p.read_text()))
    ok(not e, f"C2d {p.name} vs settlement-worksheet" + (f": {e[:3]}" if e else ""))

for p in sorted((ROOT / "fixtures/claims").glob("*.output.json")):
    e = errors(schemas["evaluation-result.schema.json"], json.loads(p.read_text()))
    ok(not e, f"C3 {p.name}" + (f": {e[:3]}" if e else ""))

for p in (ROOT / "fixtures/extraction").glob("*.json"):
    inst = {k: v for k, v in json.loads(p.read_text()).items() if not k.startswith("_")}
    e = errors(schemas["extraction-output.schema.json"], inst)
    ok(not e, f"C4 {p.name}" + (f": {e[:3]}" if e else ""))

# ---- OpenAPI ----
api = yaml.safe_load((ROOT / "api/openapi.yaml").read_text())
ok(api.get("openapi", "").startswith("3.1"), "C5 openapi version 3.1")
ops, missing_resp = [], []
for path, item in api["paths"].items():
    for method, op in item.items():
        if method in ("get", "post", "put", "patch", "delete"):
            ops.append(op.get("operationId"))
            if not op.get("responses"):
                missing_resp.append(f"{method} {path}")
ok(len(ops) == len(set(ops)) and None not in ops, f"C5 unique operationIds ({len(ops)} operations)")
ok(not missing_resp, f"C5 all operations declare responses {missing_resp or ''}")


def walk(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref":
                acc.append(v)
            else:
                walk(v, acc)
    elif isinstance(node, list):
        for v in node:
            walk(v, acc)
    return acc


def resolve_pointer(doc, pointer):
    cur = doc
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        cur = cur[part]
    return cur


bad_refs = []
for ref in walk(api, []):
    try:
        if ref.startswith("#/"):
            resolve_pointer(api, ref[1:])
        else:
            f, _, frag = ref.partition("#")
            target = json.loads((ROOT / "api" / f).resolve().read_text())
            if frag:
                resolve_pointer(target, frag)
    except Exception:  # noqa: BLE001
        bad_refs.append(ref)
ok(not bad_refs, f"C5 all $refs resolve {bad_refs or ''}")

# Build a registry so component schemas can reference each other and the external evaluation schema.
api_uri = "https://example.invalid/aw/openapi.yaml"


def rewrite(node):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/"):
                out[k] = api_uri + v
            elif k == "$ref" and isinstance(v, str) and v.startswith("../schemas/"):
                out[k] = "https://example.invalid/aw/schemas/" + v.split("/")[-1]
            else:
                out[k] = rewrite(v)
        return out
    if isinstance(node, list):
        return [rewrite(v) for v in node]
    return node


registry = Registry().with_resources([
    (api_uri, Resource.from_contents({"$schema": "https://json-schema.org/draft/2020-12/schema", "components": rewrite(api["components"])})),
    ("https://example.invalid/aw/schemas/evaluation-result.schema.json", Resource.from_contents(schemas["evaluation-result.schema.json"])),
])
n_examples = 0
for path, item in api["paths"].items():
    for method, op in item.items():
        if not isinstance(op, dict) or "requestBody" not in op:
            continue
        for ctype, media in op["requestBody"].get("content", {}).items():
            schema = rewrite(media.get("schema", {}))
            for ex_name, ex in (media.get("examples") or {}).items():
                n_examples += 1
                e = errors({"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}, ex["value"], registry)
                ok(not e, f"C6 example {op['operationId']}/{ex_name}" + (f": {e[:3]}" if e else ""))
for name, hook in api.get("webhooks", {}).items():
    for ctype, media in hook["post"]["requestBody"]["content"].items():
        for ex_name, ex in (media.get("examples") or {}).items():
            n_examples += 1
            e = errors({"$schema": "https://json-schema.org/draft/2020-12/schema", **rewrite(media["schema"])}, ex["value"], registry)
            ok(not e, f"C6 webhook example {name}/{ex_name}" + (f": {e[:3]}" if e else ""))

# ---- enum parity with DDL ----
ddl = (ROOT / "db/schema.sql").read_text()


def ddl_enum(name):
    m = re.search(rf"CREATE TYPE {name} AS ENUM \(([^;]+)\);", ddl, re.S)
    return set(re.findall(r"'([A-Z_]+)'", m.group(1))) if m else set()


ok(ddl_enum("workflow_type") == set(api["components"]["schemas"]["Workflow"]["enum"]), "C7 workflow enum parity")
ok(ddl_enum("claim_status") == set(api["components"]["schemas"]["ClaimStatus"]["enum"]), "C7 claim status enum parity")
ok(ddl_enum("doc_status") == set(api["components"]["schemas"]["Document"]["properties"]["status"]["enum"]), "C7 document status enum parity")
ok(ddl_enum("recommendation_type") == set(schemas["evaluation-result.schema.json"]["properties"]["recommendation"]["properties"]["type"]["enum"]), "C7 recommendation enum parity (DDL vs schema)")
ok(ddl_enum("disposition_type") == set(api["components"]["schemas"]["DecisionCreate"]["properties"]["disposition"]["enum"]), "C7 disposition enum parity")

ra_ddl = set(re.findall(r"'([A-Z_]+)'", re.search(r"action\s+TEXT NOT NULL CHECK \(action IN \(([^)]*)\)\)", ddl, re.S).group(1)))
ok(ra_ddl == set(api["components"]["schemas"]["ReviewerActionCreate"]["properties"]["action"]["enum"]), "C7 reviewer action parity (DDL vs API)")
ak_ddl = set(re.findall(r"'([A-Z_]+)'", re.search(r"artifact_kind\s+TEXT NOT NULL CHECK \(artifact_kind IN \(([^)]*)\)\)", ddl, re.S).group(1)))
ok(ak_ddl == set(api["components"]["schemas"]["ArtifactKind"]["enum"]), "C7 artifact kind parity (DDL vs API)")
cat_ddl = set(re.findall(r"'([A-Z_]+)'", re.search(r"category\s+TEXT NOT NULL CHECK \(category IN \(([^)]*)\)\)", ddl, re.S).group(1)))
ok(cat_ddl == set(schemas["evaluation-result.schema.json"]["$defs"]["finding"]["properties"]["category"]["enum"]), "C7 finding category parity (DDL vs schema)")
ok(set(schemas["checklist.schema.json"]["properties"]["workflow"]["enum"]) == ddl_enum("workflow_type"), "C7 checklist workflow parity")

print(json.dumps({"passed": len(passes), "failed": len(fails), "request_examples_checked": n_examples, "failures": fails}, indent=2))
sys.exit(1 if fails else 0)
