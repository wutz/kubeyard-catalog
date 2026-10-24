#!/usr/bin/env python3
"""校验 catalog 结构与清单，CI 与本地共用。

- catalog.yaml 中每个条目的 path 存在，且 addon.yaml 的名称、版本、分类一致
- schema.json 是合法 JSON Schema（能被 jsonschema 解析）
- manifests/ 下所有 YAML 可解析，且 kustomize build 通过
- 清单中的 ${var} 只能是 Flux postBuild 约定的变量
- schema 的每个顶层参数都有 x-kubeyard-target；substitute 参数必须是清单中引用的 postBuild 变量
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

import jsonschema
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWED_VARS = {"addon_namespace", "metallb_addresses"}
# 参数的去向：values 写入 addon-<name>-params 的 values.yaml，substitute 作为 postBuild 变量
TARGETS = ("values", "substitute")
errors = []


def fail(msg):
    errors.append(msg)


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


catalog = load_yaml(ROOT / "catalog.yaml")
for entry in catalog["spec"]["addons"]:
    name, path = entry["name"], ROOT / entry["path"]
    if not path.is_dir():
        fail(f"{name}: path {entry['path']} 不存在")
        continue

    addon = load_yaml(path / "addon.yaml")["spec"]
    for key in ("category", "scope", "version", "dependsOn"):
        if addon.get(key) != entry.get(key):
            fail(f"{name}: catalog.yaml 的 {key}={entry.get(key)!r} 与 addon.yaml 的 {addon.get(key)!r} 不一致")

    schema_file = path / addon.get("params", "schema.json")
    if schema_file.exists():
        try:
            jsonschema.Draft202012Validator.check_schema(json.loads(schema_file.read_text()))
        except (json.JSONDecodeError, jsonschema.SchemaError) as e:
            fail(f"{name}: schema.json 非法: {e}")
        else:
            manifest_text = "".join(p.read_text() for p in (path / "manifests").rglob("*.yaml"))
            for key, prop in json.loads(schema_file.read_text()).get("properties", {}).items():
                target = prop.get("x-kubeyard-target")
                if target not in TARGETS:
                    fail(f"{name}: 参数 {key} 缺少 x-kubeyard-target（取值 {' | '.join(TARGETS)}）")
                elif target == "substitute" and f"${{{key}" not in manifest_text:
                    fail(f"{name}: 参数 {key} 标记为 substitute，但清单中没有 ${{{key}}}")
                elif target == "substitute" and key not in ALLOWED_VARS:
                    fail(f"{name}: 参数 {key} 标记为 substitute，但不在允许的变量内")

    manifests = path / "manifests"
    for yml in manifests.rglob("*.yaml"):
        if yml.name == "kustomization.yaml":
            continue
        for doc in yaml.safe_load_all(yml.read_text()):
            if doc is None:
                continue
            if "apiVersion" not in doc or "kind" not in doc:
                fail(f"{yml.relative_to(ROOT)}: 文档缺少 apiVersion/kind")
        for var in re.findall(r"\$\{(\w+)", yml.read_text()):
            if var not in ALLOWED_VARS:
                fail(f"{yml.relative_to(ROOT)}: 未知变量 ${{{var}}}")

    if shutil.which("kustomize"):
        res = subprocess.run(["kustomize", "build", str(manifests)], capture_output=True, text=True)
        if res.returncode != 0:
            fail(f"{name}: kustomize build 失败\n{res.stderr}")
    else:
        fail("未找到 kustomize，无法执行 build 校验")

if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"OK: {len(catalog['spec']['addons'])} 个条目通过校验")
