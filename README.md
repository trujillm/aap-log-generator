# AAP Mock Service

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.68+-green.svg)](https://fastapi.tiangolo.com/)
[![OpenShift Compatible](https://img.shields.io/badge/OpenShift-Compatible-red.svg)](https://www.redhat.com/en/technologies/cloud-computing/openshift)

A **production-ready mock** providing 100% compatible **Ansible Automation Platform REST API endpoints** for development, testing, and integration on **Red Hat OpenShift**.

## Table of Contents

- [Key Features](#key-features)  
- [AAP API Endpoints](#aap-api-endpoints)
- [Quick Start](#quick-start)
- [Log Upload & Replay](#log-upload--replay)
- [OpenShift Deployment](#openshift-deployment)
- [Logging Architecture](#logging-architecture)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## Key Features

### AAP API Compatibility
- **🔌 100% Compatible REST API**: `/api/v2/jobs/`, `/api/v2/job_events/`, `/api/v2/stdout/`
- **📊 Real Job Events**: Parsed from actual AAP logs
- **🔄 Pagination**: Standard AAP pagination
- **Drop-in Replacement**: Point existing apps to this service - no code changes needed

### Log Management
- **📤 Upload Real AAP Logs**: Multi-format auto-detection (JSON, raw Ansible, system logs)
- **⚡ Log Replay**: Stream logs for Grafana Alloy/Promtail collection
- **🔄 Multi-File Replay**: Replay all files with `"id_or_path": "all"`
- **🎯 Stdout Logging**: AAP logs go to stdout → Kubernetes → Alloy → Loki (zero config!)

### Supported Log Formats
✅ JSON Event Logs • Raw Ansible Output • AAP System Logs • AWX/Tower Logs • Structured Format

**Example Files**: See `/examples/` directory (8.5KB - 169KB real AAP logs)

### Production Ready
✅ Health Checks • Persistent Storage • Security (non-root) • Helm Charts • OpenShift Native

## AAP API Endpoints

### Core AAP APIs
| Endpoint | Description |
|----------|-------------|
| `/api/v2/jobs/` | List all jobs with pagination |
| `/api/v2/jobs/{id}/` | Job details and status |
| `/api/v2/jobs/{id}/job_events/` | Job events stream (most important) |
| `/api/v2/jobs/{id}/stdout/` | Job stdout output |
| `/api/v2/job_templates/` | Job templates |

### Management APIs
| Endpoint | Description |
|----------|-------------|
| `/api/logs/upload` | Upload AAP log → auto-creates job |
| `/api/logs/replay` | Stream logs (for Alloy/Promtail) |
| `/api/replay/stop` | Stop active replay |
| `/api/status` | Current replay status |
| `/healthz` | Health check |

## Quick Start

### Local Development

```bash
# Run locally
./run-local.sh

# Upload a log file
curl -F "file=@examples/demo-job-complex.log" http://localhost:8080/api/logs/upload

# Check AAP API
curl http://localhost:8080/api/v2/jobs/ | jq .

# Start replay
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "uploaded",
    "id_or_path": "latest",
    "mode": "file",
    "rate_lines_per_sec": 50
  }'
```

### Build Container

```bash
# Build (for x86_64 clusters)
podman build --platform linux/amd64 -t quay.io/ecosystem-appeng/aap-mock:latest .

# Push
podman push quay.io/ecosystem-appeng/aap-mock:latest
```

## Log Upload & Replay

### Upload Real AAP Logs

**Where to Get AAP Logs**:
- AAP Web UI: Jobs → Download → Events/Output
- AAP CLI: `awx jobs stdout <job-id>`
- Log Files: `/var/log/tower/` or `/var/log/awx/`
- Ansible Runner: Raw `ansible-playbook` output

**Upload**:
```bash
curl -F "file=@your-aap-log.log" http://HOST/api/logs/upload
```

### Replay Logs

```bash
# Replay latest uploaded file
curl -X POST http://HOST/api/logs/replay \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "uploaded",
    "id_or_path": "latest",
    "mode": "file",
    "rate_lines_per_sec": 50,
    "loop": false
  }'

# Replay ALL uploaded files
curl -X POST http://HOST/api/logs/replay \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "uploaded",
    "id_or_path": "all",
    "mode": "file",
    "rate_lines_per_sec": 80
  }'

# Stop replay
curl -X POST http://HOST/api/replay/stop
```

### Replay Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `source` | - | `"uploaded"`, `"auto-loaded"`, or `"generated"` |
| `id_or_path` | - | `"latest"`, `"all"`, UUID, or filename |
| `mode` | `"file"` | `"file"`, `"otlp"`, or `"both"` |
| `rate_lines_per_sec` | `20` | Replay speed |
| `loop` | `false` | Continuous replay |
| `jitter_ms` | `100` | Random delay between lines |

## OpenShift Deployment

### Deploy with Helm

```bash
# Deploy
helm upgrade --install aap-mock ./chart/aap-mock \
  --namespace alm-infra-final --create-namespace \
  --set image.repository=quay.io/ecosystem-appeng/aap-mock \
  --set image.tag=latest \
  --set image.pullPolicy=Always

# Get route URL
oc get route aap-mock -n alm-infra-final -o jsonpath='{.spec.host}'

# Monitor deployment
oc rollout status deployment/aap-mock -n alm-infra-final

# View logs
oc logs -f -l app.kubernetes.io/name=aap-mock -n alm-infra-final
```

### Environment-Specific Deployments

```bash
# Development
helm upgrade --install aap-mock ./chart/aap-mock \
  -n dev-namespace \
  -f environments/values-dev.yaml

# Production
helm upgrade --install aap-mock ./chart/aap-mock \
  -n prod-namespace \
  -f environments/values-prod.yaml
```

**Namespace**: Use `helm --namespace <name>` to deploy to any namespace. Default charts use `aap-mock` namespace.

### Add Files to Running Pod

```bash
# Get pod name
POD=$(oc get pods -l app.kubernetes.io/name=aap-mock -n alm-infra-final -o name | head -n1)

# Copy single file
oc cp your-log.log $POD:/app/sample-logs/ -n alm-infra-final

# Copy directory contents
oc cp examples/. $POD:/app/sample-logs/ -n alm-infra-final

# Refresh to detect new files
curl -X POST http://YOUR_ROUTE/api/auto-loaded/refresh
```

### Cleanup

```bash
# Uninstall
helm uninstall aap-mock -n alm-infra-final

# Verify cleanup
oc get all,pvc -n alm-infra-final | grep aap-mock
```

## Logging Architecture

### Dual-Stream Logging

The app uses **two separate log streams** for clean Kubernetes log collection:

| Log Stream | Destination | Purpose |
|------------|-------------|---------|
| **AAP Mock Logs** | `stdout` → Kubernetes | Mock AAP job logs (collected by Alloy/Promtail) |
| **Application Logs** | `/var/log/aap-mock/app.log` + `stdout` (with `[APP]` prefix) | Debugging/diagnostics |

### Why This Matters

**Zero Configuration**: Grafana Alloy/Promtail automatically collect from pod stdout - no PVC mounts needed!

**Clean Separation**: Application diagnostics don't pollute your mock AAP data.

**Real-Time**: Logs appear in Loki immediately.

### View Logs

```bash
# All logs
oc logs -f -l app.kubernetes.io/name=aap-mock -n alm-infra-final

# Only AAP mock logs (what Alloy collects)
oc logs -f -l app.kubernetes.io/name=aap-mock -n alm-infra-final | grep -v "^\[APP\]"

# Only application diagnostics
oc logs -f -l app.kubernetes.io/name=aap-mock -n alm-infra-final | grep "^\[APP\]"
```

### Grafana Alloy Configuration

**Basic (Zero Config)**:
```yaml
loki.source.kubernetes "pods" {
  targets = discovery.kubernetes.pods.targets
  forward_to = [loki.write.default.receiver]
}
```

**Advanced (with label extraction)**:
```yaml
loki.process "aap_mock" {
  forward_to = [loki.write.default.receiver]
  
  stage.match {
    selector = "{app_kubernetes_io_name=\"aap-mock\"}"
    
    stage.regex {
      expression = "(?P<timestamp>\\S+) (?P<level>\\S+) \\[(?P<job_context>[^\\]]+)\\] (?P<message>.*)"
    }
    
    stage.labels {
      values = {
        level = "",
        job_context = "",
      }
    }
  }
}
```

### Loki Queries

```logql
# All AAP mock logs
{app_kubernetes_io_name="aap-mock"}

# Only AAP data (exclude app diagnostics)
{app_kubernetes_io_name="aap-mock"} !~ "\\[APP\\]"

# Errors only
{app_kubernetes_io_name="aap-mock"} |~ "ERROR"

# Specific job
{app_kubernetes_io_name="aap-mock"} |~ "\\[job_123"
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | HTTP server port |
| `PYTHONUNBUFFERED` | `1` | Python output buffering |

### Helm Values

**Key Configuration Options** (see `chart/aap-mock/values.yaml`):

```yaml
image:
  repository: quay.io/ecosystem-appeng/aap-mock
  tag: latest
  pullPolicy: Always

persistence:
  data:
    enabled: true
    size: 1Gi
  logs:
    enabled: true
    size: 1Gi

resources:
  limits:
    memory: 512Mi
    cpu: 500m

route:
  enabled: true  # OpenShift Route
```

**Environment-Specific Values**: See `environments/values-dev.yaml` and `environments/values-prod.yaml`

### File Structure

```
/
├── main.py                    # FastAPI application
├── Dockerfile                 # Container build
├── README.md                  # This file
├── run-local.sh              # Local dev script
├── sample-logs/              # Auto-loaded logs (empty by default)
├── examples/                 # Example AAP logs
├── chart/aap-mock/           # Helm chart
├── environments/             # Environment-specific configs
└── openshift/                # Manual deployment manifests
```

## Troubleshooting

### Common Issues

**Pod not starting**:
```bash
# Check logs
oc logs -l app.kubernetes.io/name=aap-mock -n alm-infra-final --tail=50

# Check events
oc get events -n alm-infra-final --sort-by='.lastTimestamp'
```

**Route not accessible**:
```bash
# Verify route
oc get route aap-mock -n alm-infra-final

# Test from within cluster
oc exec -n alm-infra-final $POD -- curl -s http://localhost:8000/healthz
```

**Logs not in Loki**:
```bash
# Check replay is active
curl http://YOUR_ROUTE/api/status

# Verify stdout output
oc logs -l app.kubernetes.io/name=aap-mock -n alm-infra-final --tail=20

# Check Alloy is running
oc get pods -n monitoring -l app=alloy
```

**Files not auto-loading**:
```bash
# List files in sample-logs
oc exec $POD -- ls -la /app/sample-logs/

# Check permissions
oc exec $POD -- ls -ld /app/sample-logs/

# Trigger refresh
curl -X POST http://YOUR_ROUTE/api/auto-loaded/refresh
```

**Volume conflicts** (RWO PVCs):
```bash
# Scale down to release PVC
oc scale deployment/aap-mock --replicas=0 -n alm-infra-final

# Wait for pods to terminate
oc wait --for=delete pod -l app.kubernetes.io/name=aap-mock -n alm-infra-final --timeout=60s

# Scale back up
oc scale deployment/aap-mock --replicas=1 -n alm-infra-final
```

### Health Checks

```bash
# Application health
curl http://YOUR_ROUTE/healthz

# Get API root
curl http://YOUR_ROUTE/api/v2/ | jq 'keys'

# Check auto-loaded files
curl http://YOUR_ROUTE/api/auto-loaded | jq .

# Check replay status
curl http://YOUR_ROUTE/api/status | jq .
```

### Debug Tips

**View application logs** (not AAP mock data):
```bash
oc logs -l app.kubernetes.io/name=aap-mock | grep "^\[APP\]"
```

**Access log files directly**:
```bash
POD=$(oc get pods -l app.kubernetes.io/name=aap-mock -o name | head -n1)
oc exec $POD -- tail -f /var/log/aap-mock/app.log
```

**Test AAP API compatibility**:
```bash
# List jobs
curl http://YOUR_ROUTE/api/v2/jobs/ | jq '.results[] | {id, name, status}'

# Get job events
curl http://YOUR_ROUTE/api/v2/jobs/1/job_events/ | jq '.results[] | {event, host, task}'

# Get job stdout
curl http://YOUR_ROUTE/api/v2/jobs/1/stdout/ | jq -r '.content' | head -20
```

## Support

### Resources
- **API Documentation**: `http://YOUR_ROUTE/docs` (FastAPI auto-generated)
- **Example Log Files**: `/examples/` directory
- **Helm Chart**: `./chart/aap-mock/`
- **Environment Configs**: `./environments/`

### Getting Help
- 📖 **Documentation**: This README
- 🐛 **Issues**: Check pod logs and events
- 💡 **Examples**: See `/examples/` for real AAP log samples

---

## Quick Reference

### Deploy & Test Flow

```bash
# 1. Deploy
helm upgrade --install aap-mock ./chart/aap-mock -n alm-infra-final --create-namespace

# 2. Get URL
HOST=$(oc get route aap-mock -n alm-infra-final -o jsonpath='{.spec.host}')

# 3. Upload log
curl -F "file=@examples/demo-job-complex.log" "http://$HOST/api/logs/upload"

# 4. Verify AAP API
curl "http://$HOST/api/v2/jobs/" | jq '.count'

# 5. Start replay
curl -X POST "http://$HOST/api/logs/replay" \
  -H "Content-Type: application/json" \
  -d '{"source":"uploaded","id_or_path":"latest","mode":"file","rate_lines_per_sec":50,"loop":true}'

# 6. Watch logs (what Alloy collects)
oc logs -f -l app.kubernetes.io/name=aap-mock -n alm-infra-final | grep -v "^\[APP\]"

# 7. Check in Loki/Grafana
# Query: {app_kubernetes_io_name="aap-mock"} !~ "\\[APP\\]"
```

---

**🎯 Built for**: Development teams needing AAP API compatibility without AAP licensing costs  
**🏗️ Platform**: Red Hat OpenShift / Kubernetes  
**🔧 Stack**: Python 3.9+, FastAPI, Helm  
**📦 Container**: `quay.io/ecosystem-appeng/aap-mock:latest`
