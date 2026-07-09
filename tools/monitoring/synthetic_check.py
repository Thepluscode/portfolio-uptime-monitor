#!/usr/bin/env python3
"""Outside-in synthetic health check — probe your service from OUTSIDE, and alert when it fails.

Your server asking itself if it feels OK will report healthy while users in another region
can't reach it. Real monitoring is outside-in. Run THIS from external vantage points — a
scheduled CI job, or (better) the same job deployed to several regions — not from the box
you're monitoring.

  python3 synthetic_check.py --url https://api.example.com/health --expect-status 200 --max-latency-ms 2000
  python3 synthetic_check.py --url https://a --url https://b --expect-body '"status":"ok"'
  python3 synthetic_check.py --url https://api.example.com/health --region eu-west-1 \
        --alert-webhook https://hooks.slack.com/services/XXX
  python3 synthetic_check.py --selftest

Exit 0 = all healthy, 1 = at least one target failed (so CI/cron flags it, and the pipeline
that scheduled it can page). On failure, POSTs a JSON alert to --alert-webhook (Slack-shaped
{"text": ...}; any generic collector accepts it too). Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def classify(result: dict, cfg: dict) -> tuple[bool, list[str]]:
    """Pure decision: is this probe healthy? Returns (ok, reasons_it_failed). Unit-tested."""
    reasons = []
    if result.get("error"):
        return False, [f"unreachable: {result['error']}"]
    if cfg.get("expect_status") is not None and result["status"] != cfg["expect_status"]:
        reasons.append(f"status {result['status']} != {cfg['expect_status']}")
    if cfg.get("max_latency_ms") is not None and result["latency_ms"] > cfg["max_latency_ms"]:
        reasons.append(f"latency {result['latency_ms']:.0f}ms > {cfg['max_latency_ms']}ms")
    if cfg.get("expect_body") and cfg["expect_body"] not in (result.get("body") or ""):
        reasons.append(f"body missing {cfg['expect_body']!r}")
    return (len(reasons) == 0), reasons


def probe(url: str, timeout: float) -> dict:
    """One outside-in request. Never raises — failure is data, not an exception."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "synthetic-check/1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(4096).decode("utf-8", "replace")
            return {"status": resp.status, "latency_ms": (time.monotonic() - start) * 1000,
                    "body": body, "error": None}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "latency_ms": (time.monotonic() - start) * 1000, "body": "", "error": None}
    except Exception as e:
        return {"status": 0, "latency_ms": (time.monotonic() - start) * 1000, "body": "", "error": str(e)}


def send_alert(webhook: str, region: str, failures: list[dict]) -> None:
    lines = [f"🔴 Synthetic check FAILED (region={region})"]
    for f in failures:
        lines.append(f"• {f['url']} — {'; '.join(f['reasons'])}")
    payload = json.dumps({"text": "\n".join(lines)}).encode()
    try:
        req = urllib.request.Request(webhook, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print(f"WARN: alert webhook failed: {e}", file=sys.stderr)


def run(urls, cfg, region, webhook, timeout) -> int:
    failures = []
    for url in urls:
        ok, reasons = classify(probe(url, timeout), cfg)
        status = "OK " if ok else "FAIL"
        print(f"  [{status}] {url}" + ("" if ok else f"  — {'; '.join(reasons)}"))
        if not ok:
            failures.append({"url": url, "reasons": reasons})
    if failures and webhook:
        send_alert(webhook, region, failures)
    print(f"{len(urls) - len(failures)}/{len(urls)} healthy (region={region})")
    return 1 if failures else 0


def selftest() -> int:
    cfg = {"expect_status": 200, "max_latency_ms": 2000, "expect_body": '"ok"'}
    assert classify({"status": 200, "latency_ms": 120, "body": '{"status":"ok"}', "error": None}, cfg)[0]
    assert not classify({"status": 500, "latency_ms": 120, "body": "", "error": None}, cfg)[0]
    assert not classify({"status": 200, "latency_ms": 9000, "body": '"ok"', "error": None}, cfg)[0]
    assert not classify({"status": 200, "latency_ms": 10, "body": "nope", "error": None}, cfg)[0]
    assert not classify({"status": 0, "latency_ms": 30000, "body": "", "error": "timed out"}, cfg)[0]
    # No expectations configured => only reachability matters.
    assert classify({"status": 204, "latency_ms": 50, "body": "", "error": None}, {})[0]
    ok, reasons = classify({"status": 503, "latency_ms": 5000, "body": "", "error": None},
                           {"expect_status": 200, "max_latency_ms": 2000})
    assert not ok and len(reasons) == 2, reasons  # both status and latency cited
    print("synthetic_check.py selftest: OK")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Outside-in synthetic health check")
    p.add_argument("--url", action="append", default=[], help="target URL (repeatable)")
    p.add_argument("--expect-status", type=int, help="required HTTP status (e.g. 200)")
    p.add_argument("--max-latency-ms", type=float, help="fail if slower than this")
    p.add_argument("--expect-body", help="substring that must appear in the body")
    p.add_argument("--timeout", type=float, default=10.0, help="per-request timeout (s)")
    p.add_argument("--region", default="local", help="vantage-point label for the alert")
    p.add_argument("--alert-webhook", help="Slack-shaped webhook to POST on failure")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.url:
        p.error("at least one --url is required")
    cfg = {"expect_status": args.expect_status, "max_latency_ms": args.max_latency_ms,
           "expect_body": args.expect_body}
    return run(args.url, cfg, args.region, args.alert_webhook, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
