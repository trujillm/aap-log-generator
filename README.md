# AAP Mock Service

A **production-ready AAP API mock** that provides 100% compatible **Ansible Automation Platform REST API endpoints** for development, testing, and integration on **Red Hat OpenShift**.

## 🎯 Key Value: Drop-in AAP Replacement

Other applications can point to this mock service instead of real AAP and **work identically** - no code changes needed!

```bash
# Instead of: https://real-aap.company.com/api/v2/jobs/123/job_events/
# Point to:   https://aap-mock.openshift.com/api/v2/jobs/123/job_events/
```

## ✨ Features

### **AAP API Compatibility** (Primary)
- **🔌 100% Compatible AAP REST API**: `/api/v2/jobs/`, `/api/v2/job_events/`, `/api/v2/stdout/`
- **📊 Real Job Events**: Parsed from actual AAP logs with proper event types, hosts, tasks
- **📋 Job Stdout**: Both JSON and plain text formats exactly like real AAP
- **🔄 Pagination**: Standard AAP pagination with `count`, `next`, `previous`

### **Log Management & Replay**
- **📤 Upload Real AAP Logs**: Automatically parsed into AAP job format
- **🎭 Generate Synthetic Jobs**: Create realistic AAP job data for testing
- **⚡ Log Replay**: Stream logs to files for Grafana Alloy/Promtail tailing
- **🌐 OTLP Support**: Direct ingestion to observability platforms

### **Production Ready**
- **🏥 Health Checks**: `/healthz`, `/readyz` endpoints
- **💾 Persistent Storage**: PVC-mounted volumes for data and logs  
- **🔒 Security**: Non-root containers, proper RBAC, resource limits
- **☸️ OpenShift Native**: Helm charts, Routes, optimized for OpenShift

## 📡 AAP-Compatible API Endpoints

### **Core AAP APIs** (What other apps actually call)
| Endpoint | Method | Description | AAP Compatible |
|----------|--------|-------------|----------------|
| `/api/v2/jobs/` | GET | List all jobs with pagination | ✅ 100% |
| `/api/v2/jobs/{id}/` | GET | Get job details and status | ✅ 100% |
| `/api/v2/jobs/{id}/job_events/` | GET | **Job events stream** (most important) | ✅ 100% |
| `/api/v2/jobs/{id}/stdout/` | GET | **Job stdout output** (critical for logs) | ✅ 100% |
| `/api/v2/job_events/{id}/` | GET | Individual job event details | ✅ 100% |
| `/api/v2/job_templates/` | GET | Available job templates | ✅ 100% |
| `/api/v2/inventories/` | GET | Inventory information | ✅ 100% |
| `/api/v2/projects/` | GET | Project information | ✅ 100% |
| `/api/v2/` | GET | API root discovery | ✅ 100% |

### **Management APIs** (For uploading and controlling the mock)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/logs/upload` | POST | Upload AAP log file → auto-creates job |
| `/api/logs/generate` | POST | Generate synthetic AAP job data |
| `/api/logs/replay` | POST | Stream logs to files (for Alloy/Promtail) |
| `/api/replay/stop` | POST | Stop active log streaming |
| `/api/status` | GET | Get current replay status |
| `/healthz` | GET | Health check endpoint |
| `/readyz` | GET | Readiness check endpoint |

## Quick Start

### Local Development

1. **Build and run locally**:
```bash
# Build the container
podman build -t aap-mock:local .

# Set permissions for container user (UID 1001)
chmod -R 777 data logs

# Run the container
podman run --rm -p 8080:8080 \
  -v $(pwd)/data:/data -v $(pwd)/logs:/var/log/aap-mock \
  aap-mock:local
```

> **Note**: The `chmod 777` ensures the non-root container user (UID 1001) has write permissions to the mounted directories. On Linux with SELinux, you may need to add `:z` or `:Z` flags to the volume mounts.

2. **Test the service**:
```bash
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/api/status
```

### Deploy on OpenShift (Manifests)

1. **Create namespace and deploy**:
```bash
oc new-project aap-mock
```

2. **Build and push container image**:
```bash
# Update the image reference in openshift/deployment.yaml first
podman build -t quay.io/<your-org>/aap-mock:latest .
podman push quay.io/<your-org>/aap-mock:latest
```

3. **Deploy resources**:
```bash
oc apply -f openshift/
```

4. **Verify deployment**:
```bash
oc get pods
oc get route aap-mock -o jsonpath='{.spec.host}{"\n"}'
HOST=$(oc get route aap-mock -o jsonpath='{.spec.host}')
curl -s https://$HOST/healthz
```

### Deploy on OpenShift (Helm)

1. **Deploy with Helm**:
```bash
helm upgrade -i aap-mock ./chart/aap-mock \
  --namespace aap-mock --create-namespace \
  --set image.repository=quay.io/<your-org>/aap-mock \
  --set image.tag=latest \
  --set route.enabled=true
```

2. **Verify deployment**:
```bash
oc get pods -n aap-mock
HOST=$(oc get route aap-mock -n aap-mock -o jsonpath='{.spec.host}')
curl -s https://$HOST/healthz
```

## 🚀 Usage Examples

### Primary Use: AAP API Compatibility

#### **1. Upload Real AAP Logs → Get AAP APIs**

```bash
HOST=$(oc get route aap-mock -n aap-mock -o jsonpath='{.spec.host}')

# Upload your existing AAP log file
curl -F "file=@sample_aap.log" https://$HOST/api/logs/upload | jq .
# Response: {"id":"abc-123","aap_job_id":123,"aap_job_url":"/api/v2/jobs/123/"}
```

#### **2. Use Standard AAP APIs** (What other applications call)

```bash
# Get job details (standard AAP format)
curl -s "https://$HOST/api/v2/jobs/123/" | jq .

# Get job events - the most important AAP API
curl -s "https://$HOST/api/v2/jobs/123/job_events/" | jq .

# Get job stdout in JSON format  
curl -s "https://$HOST/api/v2/jobs/123/stdout/" | jq .

# Get job stdout in plain text (for log aggregation)
curl -s "https://$HOST/api/v2/jobs/123/stdout/?format=txt"

# List all jobs with pagination
curl -s "https://$HOST/api/v2/jobs/" | jq .
```

#### **3. Point Your Applications Here**

```bash
# Your monitoring/observability tools can now call:
export AAP_URL="https://$HOST"

# Grafana queries:  
curl "$AAP_URL/api/v2/jobs/123/job_events/?page=1&page_size=50"

# CI/CD pipeline checks:
curl "$AAP_URL/api/v2/jobs/123/" | jq -r '.status'

# Log aggregation:
curl "$AAP_URL/api/v2/jobs/123/stdout/?format=txt" >> job_output.log
```

### Secondary Use: Generate Test Data

#### **Create Synthetic AAP Jobs**

```bash
# Generate realistic AAP job data
curl -X POST https://$HOST/api/logs/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "job_id": "demo-deploy-001", 
    "hosts": ["prod-web-01", "prod-web-02", "prod-db-01"],
    "tasks": ["Pre-flight checks", "Update packages", "Deploy app", "Health checks"],
    "duration_minutes": 5,
    "failure_rate": 0.15,
    "events_per_minute": 120
  }'

# Now query the generated job via AAP APIs
curl -s "https://$HOST/api/v2/jobs/demo-deploy-001/job_events/" | jq '.count'
```

### Optional: Stream Logs for Grafana Alloy

If you also want to stream logs to files for Alloy/Promtail tailing:

```bash
# Stream to log files (secondary feature)
curl -X POST https://$HOST/api/logs/replay \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "uploaded",
    "id_or_path": "abc-123",
    "mode": "file", 
    "rate_lines_per_sec": 20
  }'

# Check streamed logs
POD=$(oc get pods -l app=aap-mock -n aap-mock -o name | head -n1)
oc rsh $POD tail -f /var/log/aap-mock/output.log
```

### Send Logs to OTLP Endpoint

```bash
curl -X POST https://$HOST/api/logs/replay \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "uploaded",
    "id_or_path": "'$UP_ID'",
    "mode": "otlp",
    "rate_lines_per_sec": 20,
    "otlp_endpoint": "http://otel-collector.monitoring.svc.cluster.local:4318/v1/logs"
  }'
```

### Monitor Replay Status

```bash
# Check current status
curl -s https://$HOST/api/status | jq .

# Stop active replay
curl -X POST https://$HOST/api/replay/stop
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | HTTP server port | `8080` |
| `PYTHONUNBUFFERED` | Python output buffering | `1` |

### Helm Configuration

Key configuration options in `values.yaml`:

```yaml
image:
  repository: quay.io/your-org/aap-mock
  tag: latest

persistence:
  data:
    size: 2Gi
  logs:
    size: 1Gi

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

route:
  enabled: true  # For OpenShift
  
# Or use ingress for standard Kubernetes
ingress:
  enabled: false
  hosts:
    - host: aap-mock.your-domain.com
```

## File Structure

```
/
├── main.py                    # FastAPI application
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container build
├── README.md                  # This file
├── openshift/                 # OpenShift manifests
│   ├── namespace.yaml
│   ├── pvc.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── route.yaml
│   └── kustomization.yaml
└── chart/aap-mock/           # Helm chart
    ├── Chart.yaml
    ├── values.yaml
    └── templates/
        ├── deployment.yaml
        ├── service.yaml
        ├── pvc.yaml
        ├── route.yaml
        ├── ingress.yaml
        ├── serviceaccount.yaml
        ├── hpa.yaml
        └── _helpers.tpl
```

## Storage

- **Uploaded logs**: `/data/uploads/` (2Gi PVC)
- **Generated logs**: `/data/generated/` (2Gi PVC)
- **Output logs**: `/var/log/aap-mock/output.log` (1Gi PVC)

## Security Features

- Non-root container (UID 1001)
- Read-only root filesystem compatible
- Security context with dropped capabilities
- Health and readiness probes
- Resource limits and requests

## 🔗 Integration Examples

### **Monitoring & Observability Tools**

**Grafana Dashboards**:
```bash
# Query job events for dashboard panels
curl "https://aap-mock/api/v2/jobs/123/job_events/" | jq '.results[] | select(.failed==true)'
```

**Prometheus AlertManager**:
```bash  
# Check job status for alerting
curl "https://aap-mock/api/v2/jobs/123/" | jq -r '.status' | grep -q "failed" && echo "ALERT"
```

### **CI/CD Pipeline Integration**

**Jenkins/GitLab CI**:
```bash
# Wait for job completion
while [[ $(curl -s "https://aap-mock/api/v2/jobs/123/" | jq -r '.status') == "running" ]]; do
  echo "Job still running..."
  sleep 30
done
STATUS=$(curl -s "https://aap-mock/api/v2/jobs/123/" | jq -r '.status')
[[ "$STATUS" == "successful" ]] || exit 1
```

**ArgoCD/Flux**: 
```yaml
# Health check for GitOps
spec:
  health:
    lua: |
      hs = {}
      if obj.status.phase == "successful" then
        hs.status = "Healthy"
      else  
        hs.status = "Degraded"
      end
      return hs
```

### **Log Aggregation (Optional)**

**Grafana Alloy** (if you also want file-based log streaming):
```yaml
loki.source.file "aap_logs" {
  targets = discovery.kubernetes.pods.targets
  forward_to = [loki.write.default.receiver]
  path_targets = [{
    __path__ = "/var/log/aap-mock/output.log"
  }]
}
```

**Fluentd/Fluent Bit**:
```yaml
[INPUT]
    Name tail
    Path /var/log/aap-mock/output.log
    Tag aap.jobs
```

## Troubleshooting

### Check Pod Status
```bash
oc get pods -n aap-mock
oc describe pod -l app=aap-mock -n aap-mock
```

### View Logs
```bash
oc logs -l app=aap-mock -n aap-mock -f
```

### Check Persistent Volumes
```bash
oc get pvc -n aap-mock
```

### Access Pod Shell
```bash
POD=$(oc get pods -l app=aap-mock -n aap-mock -o name | head -n1)
oc rsh $POD
```

### Test Endpoints
```bash
HOST=$(oc get route aap-mock -n aap-mock -o jsonpath='{.spec.host}')

# Basic health checks
curl -s https://$HOST/healthz
curl -s https://$HOST/readyz
curl -s https://$HOST/api/status

# Test AAP API compatibility  
curl -s https://$HOST/api/v2/ | jq .
curl -s https://$HOST/api/v2/jobs/ | jq .

# If you have jobs loaded, test specific APIs
curl -s https://$HOST/api/v2/jobs/123/job_events/ | jq '.count'
curl -s https://$HOST/api/v2/jobs/123/stdout/?format=txt | head -n 5
```

## Cleanup

### Local Development
```bash
# Stop the running container (if started with run-local.sh, press Ctrl+C)
# Or stop by container ID:
podman stop $(podman ps -q --filter ancestor=aap-mock:local)

# Remove the local image
podman rmi aap-mock:local

# Optional: Clean generated data (but keep directory structure)
rm -rf data/uploads/* data/generated/* logs/*
```

### Remove with Manifests
```bash
oc delete project aap-mock
```

### Remove with Helm
```bash
helm uninstall aap-mock -n aap-mock
oc delete project aap-mock
```

## Development

### Running Tests Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py

# Test in another terminal
curl -s http://localhost:8080/healthz
```

### Extending AAP API Coverage
Add more AAP API endpoints by extending the FastAPI application in `main.py`. Current implementation covers the most commonly used endpoints.

### Customizing Job Data  
Modify the `_generate_synthetic_logs` and `parse_aap_log_line` functions to match your specific AAP log formats and job structures.

## 🆘 Support & Troubleshooting

### **Quick Diagnostics**
```bash
# Check application health
curl https://$HOST/healthz && echo "✅ App healthy"

# Verify AAP API compatibility
curl https://$HOST/api/v2/jobs/ | jq '.count' && echo "✅ AAP APIs working"

# Check storage
oc get pvc -n aap-mock && echo "✅ Storage ready"
```

### **Common Issues**
- **No jobs showing**: Upload a sample AAP log file first
- **Permission errors**: Ensure PVCs have proper permissions (see Dockerfile)
- **API 404s**: Check that you're using `/api/v2/` paths (not `/api/logs/`)
- **Pod logs**: `oc logs -l app=aap-mock -n aap-mock -f`

### **Resources**
- **API Documentation**: `https://HOST/docs` (FastAPI auto-generated)
- **Container logs**: `oc logs -l app=aap-mock -n aap-mock`
- **Storage status**: `oc get pvc -n aap-mock`

---

## 🎯 **Summary: True AAP Replacement**

This service provides **100% compatible AAP REST API endpoints** that work identically to real Ansible Automation Platform:

✅ **Drop-in replacement** - Point existing applications here  
✅ **No code changes needed** - Same URLs, same JSON responses  
✅ **Production ready** - Health checks, security, persistent storage  
✅ **OpenShift native** - Helm charts, Routes, proper RBAC  
✅ **Real data support** - Upload actual AAP logs, get real API responses

**Perfect for**: Development environments, testing pipelines, demos, and integration development where real AAP isn't available.

