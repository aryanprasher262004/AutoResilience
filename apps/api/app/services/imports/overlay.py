"""Imports in the topology (additive to autoresilience-topology/1, docs/topology.md).

- `origin` on nodes whose ownership labels carry a known import's id;
- experiment target support in import namespaces follows the import's state
  (lifecycle.target_gate) — read from the database, never from labels alone;
- `imported` on an application's view: the declared relationships (Compose
  depends_on, never verified, never drawn as edges) and planned vs. observed
  resources.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppImport
from app.schemas.imports import DeploymentPlan, ImportSpec
from app.services.imports.lifecycle import target_gate
from app.services.imports.plan import (
    IMPORT_ID_LABEL,
    LOADGEN_NAME,
    LOADGEN_SCRIPT,
    WORKLOAD_LABEL,
    is_import_namespace,
)
from app.services.topology.graph import WORKLOAD_KINDS, node_id


def annotate(db: Session, body: dict[str, Any]) -> dict[str, Any]:
    namespaces = {
        n["namespace"]
        for n in body["nodes"]
        if n["namespace"] and is_import_namespace(n["namespace"])
    }
    if not namespaces:
        return body
    imports = {
        i.namespace: i
        for i in db.scalars(
            select(AppImport).where(AppImport.namespace.in_(namespaces))
        )
    }
    for node in body["nodes"]:
        namespace = node["namespace"]
        if not namespace or namespace not in namespaces:
            continue
        imp = imports.get(namespace)
        if imp is not None and node["labels"].get(IMPORT_ID_LABEL) == str(imp.id):
            workload = node["labels"].get(WORKLOAD_LABEL)
            loadgen = workload == LOADGEN_NAME or node["name"] in (
                LOADGEN_NAME,
                LOADGEN_SCRIPT,
            )
            node["origin"] = {
                "import_id": imp.id,
                "import_name": imp.name,
                "role": "load-generator" if loadgen else "application",
                "workload": None if loadgen else workload,
            }
        if node["kind"] in WORKLOAD_KINDS and node["experiment_target"] is not None:
            reason = target_gate(db, namespace, node["name"])
            if reason is not None:
                node["experiment_target"] = {"supported": False, "reason": reason}
            elif node["experiment_target"]["supported"]:
                node["experiment_target"] = {
                    "supported": True,
                    "reason": "Imported workload, deployed and healthy; safety validation "
                    "decides whether an experiment may run.",
                }
    return body


def overlay(imp: AppImport, body: dict[str, Any]) -> dict[str, Any]:
    spec = ImportSpec.model_validate(imp.spec)
    plan = DeploymentPlan.model_validate(imp.plan)
    kinds = {w.name: w.kind for w in spec.workloads}
    ids = {n["id"] for n in body["nodes"]}
    planned = []
    for obj in plan.objects:
        if obj.kind not in ("Deployment", "StatefulSet", "Service"):
            continue
        nid = node_id(obj.kind, plan.namespace, obj.name)
        planned.append(
            {
                "id": nid,
                "kind": obj.kind,
                "name": obj.name,
                "group": obj.group,
                "observed": nid in ids,
            }
        )
    return {
        "import_id": imp.id,
        "name": imp.name,
        "status": imp.status,
        "source": imp.source,
        "namespace": imp.namespace,
        "declared": [
            {
                "type": d.type,
                "source": node_id(kinds[d.source], plan.namespace, d.source),
                "target": node_id(kinds[d.target], plan.namespace, d.target),
                "detail": d.detail,
                "verified": False,
            }
            for d in spec.declared
            if d.source in kinds and d.target in kinds
        ],
        "planned": planned,
    }
