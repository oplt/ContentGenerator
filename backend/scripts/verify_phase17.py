#!/usr/bin/env python3
"""Live-stack checks for ops Phase 17 (workflows, schema, scheduler, correlation)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import http.cookiejar
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import text

WORKFLOW_TABLES = (
    "workflow_definitions",
    "workflow_versions",
    "automations",
    "automation_targets",
    "automation_occurrences",
    "workflow_runs",
    "workflow_node_runs",
)


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object] | list[object] | str]:
    data = None
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


async def verify_schema_async() -> dict[str, object]:
    from backend.db.schema_revision import check_schema_revision
    from backend.db.session import SessionLocal

    status = check_schema_revision()
    tables: dict[str, bool] = {}
    async with SessionLocal() as db:
        for name in WORKFLOW_TABLES:
            row = await db.execute(
                text("SELECT to_regclass(:qualified) IS NOT NULL"),
                {"qualified": f"public.{name}"},
            )
            tables[name] = bool(row.scalar_one())
    missing = [name for name, ok in tables.items() if not ok]
    return {
        "schema_at_head": status.ok,
        "current_revision": status.current,
        "expected_heads": list(status.expected_heads),
        "workflow_tables": tables,
        "workflow_tables_ok": not missing,
        "missing_tables": missing,
    }


def verify_api(base_url: str, email: str, password: str) -> dict[str, object]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def _call(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object] | list[object] | str]:
        data = None
        req_headers = {"Content-Type": "application/json", **(headers or {})}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with opener.open(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw

    sign_in_url = f"{base_url.rstrip('/')}/api/v1/auth/sign-in"
    code, payload = _call(
        "POST",
        sign_in_url,
        body={"email": email, "password": password, "remember_me": True},
    )
    if code != 200 or not isinstance(payload, dict):
        return {"sign_in_ok": False, "sign_in_status": code, "payload": payload}

    user = payload.get("user")
    if not isinstance(user, dict):
        return {"sign_in_ok": False, "detail": "missing user in session"}
    tenant_id = user.get("default_tenant_id")
    if not tenant_id:
        memberships = user.get("memberships")
        if isinstance(memberships, list) and memberships:
            first = memberships[0]
            if isinstance(first, dict):
                tenant_id = first.get("tenant_id")

    correlation_id = f"phase17-script-{int(datetime.now(timezone.utc).timestamp())}"
    endpoints: dict[str, object] = {}
    for suffix in ("workflows/definitions", "workflows/automations", "workflows/runs"):
        url = f"{base_url.rstrip('/')}/api/v1/{suffix}"
        status, body = _call(
            "GET",
            url,
            headers={
                "X-Tenant-ID": str(tenant_id),
                "X-Correlation-ID": correlation_id,
            },
        )
        endpoints[suffix] = {
            "status": status,
            "is_list": isinstance(body, list),
            "ok": status == 200 and isinstance(body, list),
        }

    # Fresh client without session cookies — correlation must still echo on 401.
    def _unauth_call() -> tuple[int, dict[str, object] | list[object] | str]:
        data = None
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/v1/workflows/definitions",
            data=data,
            headers={"X-Correlation-ID": "phase17-unauth-correlation"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw

    err_status, err_body = _unauth_call()
    err_corr = None
    if isinstance(err_body, dict):
        error = err_body.get("error")
        if isinstance(error, dict):
            err_corr = error.get("correlation_id")

    endpoints_ok = all(
        isinstance(row, dict) and row.get("ok") is True for row in endpoints.values()
    )
    return {
        "sign_in_ok": True,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "workflow_endpoints": endpoints,
        "workflow_endpoints_ok": endpoints_ok,
        "unauth_status": err_status,
        "unauth_correlation_id": err_corr,
    }


async def verify_scheduler_cycles(cycles: int) -> dict[str, object]:
    from backend.db.session import SessionLocal
    from backend.modules.workflows.scheduler import AutomationScheduler

    outcomes: list[int] = []
    async with SessionLocal() as db:
        scheduler = AutomationScheduler(db)
        for _ in range(cycles):
            results = await scheduler.tick(
                now=datetime.now(timezone.utc),
                enqueue_advance=False,
            )
            outcomes.append(len(results))
        await db.commit()
    return {"cycles": cycles, "claimed_counts": outcomes, "scheduler_ok": True}


async def _build_report(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema": await verify_schema_async(),
        "api": verify_api(args.base_url, args.email, args.password),
        "scheduler": await verify_scheduler_cycles(args.scheduler_cycles),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 17 live verification")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="demo@example.com")
    parser.add_argument("--password", default="password1234")
    parser.add_argument("--scheduler-cycles", type=int, default=3)
    args = parser.parse_args()

    report: dict[str, object] = asyncio.run(_build_report(args))
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")

    schema = cast(dict[str, object], report["schema"])
    scheduler = cast(dict[str, object], report["scheduler"])
    api = cast(dict[str, object], report["api"])
    schema_ok = bool(schema.get("workflow_tables_ok")) and bool(schema.get("schema_at_head"))
    scheduler_ok = bool(scheduler.get("scheduler_ok"))
    corr_ok = api.get("unauth_correlation_id") == "phase17-unauth-correlation"
    api_ok = bool(api.get("workflow_endpoints_ok"))
    return 0 if schema_ok and scheduler_ok and corr_ok and api_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
