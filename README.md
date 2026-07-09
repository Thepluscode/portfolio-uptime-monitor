# portfolio-uptime-monitor

One free, outside-in uptime probe for every **private** service in the portfolio.

## Why

A scheduled GitHub Action *inside* a private repo burns billable Actions minutes. A scheduled
Action in a **public** repo is free and unlimited — and probing from here is a genuine external
vantage point (the whole premise of Q1 outside-in monitoring: the service asking itself if it's
healthy can't tell you users can't reach it).

## What it does

Every 5 minutes, `tools/monitoring/synthetic_check.py` probes every URL in the `MONITOR_TARGETS`
secret (status 200 + latency), and on any failure POSTs `ALERT_WEBHOOK` and fails the job.

## Setup

Settings → Secrets and variables → Actions → **Secrets**:

| Secret | Value |
|--------|-------|
| `MONITOR_TARGETS` | space/newline-separated public health URLs of the private services |
| `ALERT_WEBHOOK` | Slack / PagerDuty inbound webhook |

Targets to add (fill in each service's real prod domain):

```
https://<e-a-b-api>/health
https://<agent-verifier>/health
https://<clone-to-close>/health
https://<edgeforge>/health
https://<controlplane>/health
https://<bughawk>/healthz
https://<antivirus>/            # no /health endpoint yet — probes root
```

Targets stay in the secret, never committed, so no private domain is exposed in this public repo.

## Alternative: a hosted SaaS monitor

If you'd rather not run this Action, the same `synthetic_check.py` list maps 1:1 onto a free
UptimeRobot account (50 monitors, 5-min interval, email/Slack alerts) — one monitor per URL above,
"keyword" set to the body marker where the service has one.
