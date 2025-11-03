# AAP Mock Service

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.68+-green.svg)](https://fastapi.tiangolo.com/)
[![OpenShift Compatible](https://img.shields.io/badge/OpenShift-Compatible-red.svg)](https://www.redhat.com/en/technologies/cloud-computing/openshift)

A **production-ready AAP API mock** that provides 100% compatible **Ansible Automation Platform REST API endpoints** for development, testing, and integration on **Red Hat OpenShift**.

## Table of Contents

- [Key Value](#key-value)
- [Features](#features)  
- [Can I Use Real AAP Logs?](#can-i-use-real-aap-logs)
- [AAP-Compatible API Endpoints](#aap-compatible-api-endpoints)
- [Quick Start](#quick-start)
- [Usage Examples](#usage-examples)
- [Log Replay Functionality](#log-replay-functionality)
- [Integration Examples](#integration-examples)
- [OpenShift File Management](#openshift-file-management)
- [Configuration](#configuration)
- [Support](#support)

## Key Value

**Drop-in AAP Replacement** - Other applications can point to this mock service instead of real AAP and **work identically** - no code changes needed!

```bash
# Instead of: https://real-aap.company.com/api/v2/jobs/123/job_events/
# Point to:   https://aap-mock.openshift.com/api/v2/jobs/123/job_events/
```

## Features

### **AAP API Compatibility** (Primary)
- **🔌 100% Compatible AAP REST API**: `/api/v2/jobs/`, `/api/v2/job_events/`, `/api/v2/stdout/`
- **📊 Real Job Events**: Parsed from actual AAP logs with proper event types, hosts, tasks
- **📋 Job Stdout**: Both JSON and plain text formats exactly like real AAP
- **🔄 Pagination**: Standard AAP pagination with `count`, `next`, `previous`

### **Log Management & Replay**
- **📤 Upload Real AAP Logs**: **Multi-format support** - automatically detects and parses various AAP log formats
- **🎭 Generate Synthetic Jobs**: Create realistic AAP job data for testing
- **⚡ Log Replay**: Stream logs to files for Grafana Alloy/Promtail tailing
- **🔄 Multi-File Replay**: Replay all uploaded files or all auto-loaded files with `"id_or_path": "all"`
- **🌐 OTLP Support**: Direct ingestion to observability platforms

### **Supported AAP Log Formats** 📋
✅ **JSON Event Logs**: `{"event": "runner_on_start", "counter": 1, ...}` - Direct AAP event exports  
✅ **Raw Ansible Output**: `TASK [setup] ***`, `ok: [host]`, `failed: [host]` - Playbook execution logs  
✅ **AAP System Logs**: `2024-01-15 10:30:00 INFO Job 123 started` - AAP controller logs  
✅ **AWX/Tower Logs**: `Jan 15 10:30:00 tower-01 awx-manage[1234]: Job started` - System/service logs  
✅ **Structured Format**: `2024-01-15T10:30:00.000Z INFO [job_123:host] MESSAGE` - Custom format

**📁 Example Files Available**: See `/examples/` directory for real-world log samples:
- `examples/demo-job-failed.log` - Failed AAP job with error handling (8.5K)
- `examples/demo-job-complex.log` - Complex multi-task AAP job (169K) 
- `examples/aap_job_events.json` - AAP JSON event format
- `examples/ansible_playbook.log` - Raw ansible-playbook output  
- `examples/aap_system.log` - AAP controller/system logs
- `examples/tower_awx.log` - AWX/Tower service logs

## Can I Use Real AAP Logs?

**✅ YES!** You can take log files directly from your AAP instance and upload them:

### **Where to Get Real AAP Logs**:
1. **AAP Web UI**: Jobs → Select Job → Download → Events (JSON) or Output (Text)
2. **AAP CLI**: `awx jobs stdout <job-id>` or `awx job_events list --job <job-id>`
3. **AAP Log Files**: `/var/log/tower/` or `/var/log/awx/` on AAP controllers
4. **Ansible Runner**: Raw playbook execution output from `ansible-playbook` commands
5. **System Logs**: AAP service logs from journald or syslog

### **How to Use Your Real AAP Logs**:

Once you have real AAP log files, you can use them in **two ways**:

1. **📁 Drop in `sample-logs/` directory** (recommended for teams/development)
2. **📤 Upload via API** (for runtime/dynamic scenarios)

👉 **See detailed examples in the [Usage Examples](#usage-examples) section below**

**The app will auto-detect any AAP log format and create proper AAP API responses from your real logs!**

### **Production Ready**
- **🏥 Health Checks**: `/healthz`, `/readyz` endpoints
- **💾 Persistent Storage**: PVC-mounted volumes for data and logs  
- **🔒 Security**: Non-root containers, proper RBAC, resource limits
- **☸️ OpenShift Native**: Helm charts, Routes, optimized for OpenShift

## AAP-Compatible API Endpoints

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
| `/api/auto-loaded` | GET | List auto-loaded log files |
| `/healthz` | GET | Health check endpoint |
| `/readyz` | GET | Readiness check endpoint |

## Quick Start

### Local Development

#### **🚀 Easy Way (Recommended)**

Just run our convenience script - it handles everything:

```bash
./run-local.sh
```

The script will:
- ✅ Build the container image  
- ✅ Set proper permissions
- ✅ Start the service on http://localhost:8080
- ✅ Mount data and logs directories correctly

#### **⚙️ Manual Way (Advanced)**

If you prefer to run commands manually:

```bash
# Build the container
podman build -t aap-mock:local .

# Create directories and set permissions  
mkdir -p data/uploads data/generated logs
chmod -R 777 data logs

# Run with proper user permissions (IMPORTANT!)
podman run --rm -p 8080:8080 --user $(id -u):$(id -g) \
  -v $(pwd)/data:/data -v $(pwd)/logs:/var/log/aap-mock \
  aap-mock:local
```

> **Note**: `$(pwd)` gets your current directory path, and `$(id -u):$(id -g)` runs the container as your user to avoid permission issues.

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

### Deploy on OpenShift (Helm) 🎯

**Recommended deployment method** - One command installs everything with full configurability.

#### **🚀 Quick Start - Any Namespace**

Deploy to **any namespace** you want (creates namespace if it doesn't exist):

```bash
# Deploy to default 'aap-mock' namespace
helm upgrade --install aap-mock ./chart/aap-mock \
  --namespace aap-mock --create-namespace

# Deploy to your custom namespace  
helm upgrade --install my-aap-service ./chart/aap-mock \
  --namespace my-team-tools --create-namespace

# Deploy to existing namespace
helm upgrade --install aap-mock-dev ./chart/aap-mock \
  --namespace development
```

#### **⚙️ Configuration Options**

**Essential configurations for different environments:**

```bash
# Production deployment with custom settings
helm upgrade --install aap-mock-prod ./chart/aap-mock \
  --namespace production --create-namespace \
  --set image.repository=quay.io/your-org/aap-mock \
  --set image.tag=v1.2.0 \
  --set replicaCount=3 \
  --set resources.limits.memory=1Gi \
  --set persistence.data.size=10Gi \
  --set persistence.logs.size=5Gi \
  --set route.enabled=true

# Development deployment (lightweight)  
helm upgrade --install aap-mock-dev ./chart/aap-mock \
  --namespace dev-team --create-namespace \
  --set resources.limits.memory=256Mi \
  --set persistence.data.size=1Gi \
  --set persistence.logs.size=500Mi

# With custom environment variables
helm upgrade --install aap-mock ./chart/aap-mock \
  --namespace aap-mock --create-namespace \
  --set app.env.OTLP_ENDPOINT="http://otel-collector:4318/v1/logs" \
  --set app.env.LOG_LEVEL="DEBUG"
```

#### **📋 Common Configuration Values**

| **Parameter** | **Description** | **Default** | **Example** |
|---------------|-----------------|-------------|-------------|
| `image.repository` | Container image repository | `quay.io/matrujil/aap-mock` | `quay.io/your-org/aap-mock` |
| `image.tag` | Image tag to deploy | `x86_64` | `latest`, `v1.0.0` |
| `replicaCount` | Number of replicas | `1` | `3` (production) |
| `persistence.data.size` | Upload storage size | `2Gi` | `10Gi` (production) |
| `persistence.logs.size` | Output log storage size | `1Gi` | `5Gi` (production) |
| `resources.limits.memory` | Memory limit | `512Mi` | `1Gi`, `2Gi` |
| `route.enabled` | Create OpenShift Route | `true` | `false` (use ingress) |
| `app.env.*` | Environment variables | `{}` | Custom config |

#### **🔍 Verification & Access**

**Check deployment status:**
```bash
# Check all resources in your namespace
helm status aap-mock -n aap-mock
oc get all,pvc -n aap-mock

# Get service URL
HOST=$(oc get route aap-mock -n aap-mock -o jsonpath='{.spec.host}')
echo "Service URL: http://$HOST"

# Test health
curl -s "http://$HOST/healthz"
curl -s "http://$HOST/api/status" | jq '.'
```

#### **📂 Namespace Management**

**Multiple environments in separate namespaces:**

```bash
# Development environment
helm upgrade --install aap-mock-dev ./chart/aap-mock \
  --namespace development --create-namespace \
  --values environments/values-dev.yaml

# Staging environment  
helm upgrade --install aap-mock-staging ./chart/aap-mock \
  --namespace staging --create-namespace \
  --values environments/values-staging.yaml

# Production environment
helm upgrade --install aap-mock-prod ./chart/aap-mock \
  --namespace production --create-namespace \
  --values environments/values-prod.yaml
```

**List deployments across namespaces:**
```bash
helm list --all-namespaces | grep aap-mock
```

#### **🔧 Advanced Configuration**

**Use the provided environment-specific values files:**

```bash
# Ready-to-use values files are provided in environments/
ls environments/
# README.md  values-dev.yaml  values-prod.yaml

# Development deployment (lightweight)
helm upgrade --install aap-mock-dev ./chart/aap-mock \
  --namespace development --create-namespace \
  --values environments/values-dev.yaml

# Production deployment (HA + security)  
helm upgrade --install aap-mock-prod ./chart/aap-mock \
  --namespace production --create-namespace \
  --values environments/values-prod.yaml

# Create custom environment (e.g., staging)
cp environments/values-prod.yaml environments/values-staging.yaml
# Edit environments/values-staging.yaml as needed
helm upgrade --install aap-mock-staging ./chart/aap-mock \
  --namespace staging --create-namespace \
  --values environments/values-staging.yaml
```

**📖 See `environments/README.md` for detailed configuration options and best practices.**

#### **🚨 Troubleshooting Helm Deployments**

**Common issues and solutions:**

```bash
# Check Helm deployment status
helm status aap-mock -n aap-mock

# View recent Helm history
helm history aap-mock -n aap-mock

# Debug failed deployments
oc get events -n aap-mock --sort-by=.metadata.creationTimestamp
oc describe pod -l app.kubernetes.io/name=aap-mock -n aap-mock

# Pod won't start (security context)
# Solution: Let OpenShift assign user IDs automatically (already configured)

# PVC issues
oc get pvc -n aap-mock
oc describe pvc aap-mock-data -n aap-mock

# Image pull issues  
oc describe pod <pod-name> -n aap-mock
# Check image repository and tag in values

# Route not accessible
oc get route aap-mock -n aap-mock
# Check if route is created and service is running
```

#### **🗑️ Cleanup**

**Remove deployment:**
```bash
# Remove from specific namespace
helm uninstall aap-mock -n aap-mock

# Remove multiple environments
helm uninstall aap-mock-dev -n development  
helm uninstall aap-mock-staging -n staging
helm uninstall aap-mock-prod -n production

# Verify cleanup
oc get all,pvc -n aap-mock
```

## Usage Examples

### Primary Use: AAP API Compatibility

There are **two ways** to get your AAP logs into the mock service:

### **📁 The `sample-logs/` Directory**

The `./sample-logs/` directory is a **special folder** where you can **drop log files for permanent auto-loading**:

- 📂 **What it is**: A directory in your project that gets mounted into the container
- 🔄 **Auto-loading**: Any `.log` or `.txt` files here are **automatically processed on startup**
- 👥 **Team sharing**: Files are **version-controlled** and shared with your team
- 🎯 **Simple names**: Reference files by name (like `my-job`) instead of UUIDs
- 🚀 **Instant replay**: No upload step needed - files are always available

**📝 Note**: The `sample-logs/` directory starts **empty** - you add your own files. **Demo files are available in `examples/` for reference.**

### **When to Use Which Method:**

| **Use `sample-logs/` when:** | **Use Upload API when:** |
|-------------------------------|---------------------------|
| ✅ Working with **team members** | ✅ **One-time testing** with random logs |
| ✅ **Reproducible testing** scenarios | ✅ **Dynamic log generation** from CI/CD |
| ✅ **Long-term development** | ✅ **External systems** uploading logs |
| ✅ Want **simple names** for replay | ✅ Need **temporary** log processing |
| ✅ **OpenShift `oc cp` file additions** | ✅ **Runtime file uploads** |

### **🔄 Runtime File Refresh**

**Added files after startup?** Use the refresh endpoint to detect new files without restarting:

```bash
# Add files to sample-logs directory (locally or in OpenShift)
cp new-job.log sample-logs/

# Refresh to detect new files (works in any environment!)
curl -X POST http://localhost:8080/api/auto-loaded/refresh | jq .

# New files are now available for replay
curl http://localhost:8080/api/auto-loaded | jq .
```

**🎯 Perfect for OpenShift scenarios:**
- ConfigMap updates
- PersistentVolume file additions  
- InitContainer file loading
- Operator-managed file updates

---

### **📝 Quick Summary:**

- 📁 **`sample-logs/` directory** = Drop files here → auto-loaded on startup → use simple names
- 📤 **Upload API** = Send files via HTTP → get UUID back → use UUID for replay

---

#### **🚀 Method 1: Auto-Loading from `sample-logs/` (Recommended)**

**Drop files once, use forever!** Place log files in `./sample-logs/` directory and they're automatically loaded on startup:

```bash
# Option A: Add your real AAP logs
cp your-real-job.log ./sample-logs/my-production-job.log

# Option B: Use demo files from examples (optional)
cp examples/demo-job-failed.log ./sample-logs/
cp examples/demo-job-complex.log ./sample-logs/

# Start the service (auto-loads all files)
./run-local.sh

# That's it! AAP APIs are immediately available:
curl "http://localhost:8080/api/v2/jobs/" | jq .
curl "http://localhost:8080/api/v2/jobs/1/job_events/" | jq .

# Simple replay by filename (no complex IDs!)
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{"source":"auto-loaded","id_or_path":"demo-job-failed","mode":"file"}'
```

**💡 Pro Tip**: Check `examples/` directory for ready-to-use demo log files you can copy to `sample-logs/` if needed!

**✅ Benefits**: Team sharing, version control, no upload step, instant replay

**📋 List auto-loaded files**:
```bash
curl "http://localhost:8080/api/auto-loaded" | jq .
# Shows: {"count": 2, "files": [{"key": "demo-job-failed", "filename": "demo-job-failed.log"}, ...]}
```

**📁 Demo Files Available**: Ready-to-use AAP logs are in `./examples/`:
- `demo-job-failed.log` - Failed AAP job with error handling  
- `demo-job-complex.log` - Complex multi-task AAP job
- Copy any to `./sample-logs/` if you want them auto-loaded!

#### **📤 Method 2: Upload API (For Dynamic/Temporary Logs)**

**For runtime uploads from external systems or one-time testing**. Files are uploaded via API call and get temporary UUIDs:

**✅ Works with ANY AAP log format! The app auto-detects and parses:**

```bash
HOST=$(oc get route aap-mock -n aap-mock -o jsonpath='{.spec.host}')

# Upload ANY of these AAP log formats:
curl -F "file=@aap_job_events.json" https://$HOST/api/logs/upload    # JSON events
curl -F "file=@ansible_playbook.log" https://$HOST/api/logs/upload   # Raw ansible output  
curl -F "file=@aap_system.log" https://$HOST/api/logs/upload         # AAP system logs
curl -F "file=@tower_awx.log" https://$HOST/api/logs/upload          # AWX/Tower logs

# All return the same response format:
# {"id":"abc-123","aap_job_id":123,"aap_job_url":"/api/v2/jobs/123/"}
```

**The app automatically:**
- 🔍 **Detects** the log format (JSON, raw ansible, system logs, etc.)
- 🔄 **Parses** events, hosts, tasks, timestamps, failures
- 🏗️ **Creates** AAP-compatible job data with proper event structure
- 🚀 **Exposes** standard AAP REST APIs instantly

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
POD=$(oc get pods -l app.kubernetes.io/name=aap-mock -n aap-mock -o name | head -n1)
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

## OpenShift File Management

### **Adding Log Files in OpenShift Environments**

The refresh endpoint makes it easy to add log files in OpenShift without pod restarts:

#### **Method 1: Direct File Copy (Easiest)**
```bash
# Copy files directly into running pod (recommended)
POD=$(oc get pods -l app.kubernetes.io/name=aap-mock -o name | head -n1)

# Copy single files
oc cp your-log-file.log $POD:/app/sample-logs/
oc cp examples/demo-job-failed.log $POD:/app/sample-logs/

# OR copy entire directory
oc cp examples/ $POD:/app/sample-logs/

# Refresh to detect new files
curl -X POST https://your-aap-mock-route/api/auto-loaded/refresh
```

#### **Method 2: ConfigMap Updates (Advanced)**
```bash
# Create/update ConfigMap with log files  
oc create configmap aap-logs --from-file=sample-logs/ --dry-run=client -o yaml | oc apply -f -

# Refresh the application (no restart needed!)
curl -X POST https://your-aap-mock-route/api/auto-loaded/refresh
```

#### **Method 3: InitContainer Loading**
```yaml
# In your deployment.yaml
initContainers:
- name: load-logs
  image: alpine/curl
  command: ["/bin/sh", "-c"]
  args:
    - |
      # Download logs from external source
      curl -o /shared/production-job.log https://logs.example.com/latest.log
      # Trigger refresh after loading
      sleep 10 && curl -X POST http://aap-mock:8080/api/auto-loaded/refresh
  volumeMounts:
  - name: sample-logs
    mountPath: /shared
```

#### **Method 4: Operator Integration**
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: update-aap-logs
spec:
  template:
    spec:
      containers:
      - name: update-logs
        image: alpine/curl
        command: ["/bin/sh", "-c"]
        args:
          - |
            # Update ConfigMap or PV with new logs
            # Then refresh the application
            curl -X POST http://aap-mock.aap-mock.svc.cluster.local:8080/api/auto-loaded/refresh
      restartPolicy: Never
```

### **OpenShift Deployment Examples**

#### **Standard Deployment (Recommended)**  
```bash
# Deploy with PV for easy file additions
helm upgrade -i aap-mock ./chart/aap-mock \
  --set persistence.enabled=true \
  --set persistence.size=1Gi

# Then easily add files anytime:
POD=$(oc get pods -l app.kubernetes.io/name=aap-mock -o name | head -n1) 

# Copy single file
oc cp your-log.log $POD:/app/sample-logs/

# Copy entire directory 
oc cp examples/ $POD:/app/sample-logs/

curl -X POST https://your-route/api/auto-loaded/refresh
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | HTTP server port | `8080` |
| `PYTHONUNBUFFERED` | Python output buffering | `1` |

### Helm Configuration

**📖 For detailed Helm configuration, see the comprehensive [Deploy on OpenShift (Helm)](#deploy-on-openshift-helm-) section above.**

**Quick reference - key values.yaml options:**

- `image.repository` / `image.tag` - Container image to deploy
- `persistence.data.size` / `persistence.logs.size` - Storage sizes  
- `resources.limits.memory` - Memory allocation
- `route.enabled` - OpenShift Route creation
- `app.env.*` - Custom environment variables
- **Namespace**: Managed via `helm --namespace <name> --create-namespace`

## File Structure

```
/
├── main.py                    # FastAPI application with multi-format parsing
├── Dockerfile                 # Container build configuration  
├── README.md                  # Complete documentation
├── run-local.sh              # Local development script
├── sample-logs/              # Auto-loaded log files (empty by default)
├── examples/                 # Real AAP log format examples
│   ├── aap_job_events.json    # AAP JSON event format
│   ├── ansible_playbook.log   # Raw ansible-playbook output
│   ├── aap_system.log         # AAP controller/system logs
│   ├── tower_awx.log          # AWX/Tower service logs
│   ├── demo-job-complex.log   # Complex multi-task AAP job
│   └── demo-job-failed.log    # Failed job example
├── environments/             # Environment-specific Helm values
│   ├── README.md              # Environment deployment guide
│   ├── values-dev.yaml        # Development configuration
│   └── values-prod.yaml       # Production configuration
├── openshift/                # OpenShift manifests (for manual deployment)
│   ├── namespace.yaml
│   ├── pvc.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── route.yaml
│   └── kustomization.yaml
├── chart/aap-mock/          # Helm chart (recommended deployment)
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── pvc.yaml
│       ├── route.yaml
│       ├── ingress.yaml
│       ├── serviceaccount.yaml
│       ├── hpa.yaml
│       └── _helpers.tpl
├── data/                    # Runtime directories (created by container)
│   ├── uploads/              # API uploaded files
│   └── generated/            # Generated mock logs  
└── logs/                    # Output logs directory
    └── output.log            # Structured AAP format output
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

## Log Replay Functionality

### What is Log Replay?

**Log Replay** streams your uploaded or auto-loaded AAP logs line-by-line to simulate real-time job execution. This is perfect for:

- **📊 Testing log aggregation** (Grafana Alloy, Promtail, Fluentd)
- **🔍 Observability platform integration** (Loki, OpenTelemetry)
- **⚡ Real-time monitoring demos** 
- **🧪 Load testing log ingestion pipelines**

### Prerequisites

Before using replay functionality:

1. **✅ Application is running**: Use `./run-local.sh` or deploy to OpenShift
2. **✅ Log files available**: Either upload via API or place in `sample-logs/` directory
3. **✅ Output destination ready**: File system or OTLP endpoint

### Replay Modes

| Mode | Output Destination | Use Case |
|------|-------------------|----------|
| `file` | `/var/log/aap-mock/output.log` | Grafana Alloy, Promtail file tailing |
| `otlp` | HTTP endpoint (configurable) | Direct to OpenTelemetry Collector |
| `both` | File + OTLP simultaneously | Dual ingestion for testing |

### Basic Replay Commands

#### 1. Replay Auto-loaded Files (Simplest)

```bash
# First, copy demo files from examples (if you want to try them)
cp examples/demo-job-failed.log sample-logs/
cp examples/demo-job-complex.log sample-logs/

# Refresh to load the new files
curl -X POST http://localhost:8080/api/auto-loaded/refresh

# List available auto-loaded files
curl "http://localhost:8080/api/auto-loaded" | jq .

# Option A: Replay ALL auto-loaded files sequentially
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{
    "source": "auto-loaded",
    "id_or_path": "all", 
    "mode": "file",
    "rate_lines_per_sec": 30
  }'

# Option B: Replay one specific file by name
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{
    "source": "auto-loaded",
    "id_or_path": "demo-job-failed", 
    "mode": "file",
    "rate_lines_per_sec": 20
  }'
```

#### 2. Replay Uploaded Files (Super Simple!)

```bash
# Step 1: Upload your file
curl -F "file=@your-aap-job.log" http://localhost:8080/api/logs/upload

# Step 2: Replay the latest uploaded file (no UUID needed!)
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{
    "source": "uploaded",
    "id_or_path": "latest",
    "mode": "file",
    "rate_lines_per_sec": 30
  }'
```

✅ **That's it!** The `"latest"` keyword automatically finds your most recently uploaded file.

**One-liner for maximum simplicity:**
```bash
curl -F "file=@your-aap-job.log" http://localhost:8080/api/logs/upload && \
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{"source":"uploaded","id_or_path":"latest","mode":"file","rate_lines_per_sec":30}'
```

**Advanced: Replay specific uploaded file by UUID**
```bash
# If you need to replay a specific upload (not the latest)
FILE_ID=$(curl -F "file=@your-aap-job.log" http://localhost:8080/api/logs/upload | jq -r '.id')
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d "{\"source\":\"uploaded\",\"id_or_path\":\"$FILE_ID\",\"mode\":\"file\",\"rate_lines_per_sec\":30}"
```

#### 3. OTLP Integration (Advanced)

```bash
# First ensure you have files in sample-logs (copy from examples if needed)
# cp examples/demo-job-complex.log sample-logs/
# curl -X POST http://localhost:8080/api/auto-loaded/refresh

# Stream directly to OpenTelemetry Collector
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{
    "source": "auto-loaded",
    "id_or_path": "demo-job-complex",
    "mode": "otlp",
    "rate_lines_per_sec": 50,
    "otlp_endpoint": "http://otel-collector:4318/v1/logs"
  }'
```

### Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source` | string | - | `"uploaded"`, `"generated"`, or `"auto-loaded"` |
| `id_or_path` | string | - | File identifier: `"latest"` (for most recent upload), UUID (specific upload), or name (auto-loaded) |
| `mode` | string | `"file"` | `"file"`, `"otlp"`, or `"both"` |
| `rate_lines_per_sec` | int | `20` | Replay speed (lines per second) |
| `loop` | bool | `false` | Repeat replay continuously |
| `jitter_ms` | int | `100` | Random delay between lines (milliseconds) |
| `otlp_endpoint` | string | `null` | OTLP HTTP endpoint URL |

#### Special `id_or_path` Values

| Value | Source | Description | Example |
|-------|--------|-------------|---------|
| `"all"` | `auto-loaded` | Replay all auto-loaded files sequentially | `"id_or_path": "all"` |
| `"all"` | `uploaded` | Replay all uploaded files sequentially | `"id_or_path": "all"` |
| `"latest"` | `uploaded` | Most recently uploaded file | `"id_or_path": "latest"` |
| `UUID` | `uploaded` | Specific uploaded file | `"id_or_path": "dcef653c-c73e-4c2e..."` |
| `filename` | `auto-loaded` | File from sample-logs directory | `"id_or_path": "my-job"` |
| `job-id` | `generated` | Generated synthetic job | `"id_or_path": "test-job-001"` |

### Advanced Replay Examples

#### Replay All Auto-loaded Files (Complete Test Suite)
```bash
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{
    "source": "auto-loaded",
    "id_or_path": "all",
    "mode": "file",
    "rate_lines_per_sec": 50
  }'
```
✨ **Perfect for comprehensive testing!** Replays all files in `sample-logs/` directory sequentially.

#### Replay All Uploaded Files (Multi-File Upload Testing)
```bash
# First upload multiple files
curl -F "file=@job1.log" http://localhost:8080/api/logs/upload
curl -F "file=@job2.log" http://localhost:8080/api/logs/upload
curl -F "file=@job3.log" http://localhost:8080/api/logs/upload

# Then replay all uploaded files sequentially with looping
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{
    "source": "uploaded",
    "id_or_path": "all",
    "mode": "file",
    "rate_lines_per_sec": 30,
    "loop": true
  }'
```
🎯 **Great for testing file upload workflows!** Cycles through all uploaded files continuously.

#### Slow Replay with Looping (Latest Upload)
```bash
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{
    "source": "uploaded",
    "id_or_path": "latest",
    "mode": "file",
    "rate_lines_per_sec": 5,
    "loop": true,
    "jitter_ms": 200
  }'
```

#### High-Speed Load Testing
```bash
# Note: This example assumes you have demo-job-complex in sample-logs/
# Copy from examples if needed: cp examples/demo-job-complex.log sample-logs/
curl -X POST http://localhost:8080/api/logs/replay \
  -H 'content-type: application/json' \
  -d '{
    "source": "auto-loaded", 
    "id_or_path": "demo-job-complex",
    "mode": "both",
    "rate_lines_per_sec": 100,
    "otlp_endpoint": "http://localhost:4318/v1/logs"
  }'
```

### Monitoring Replay

#### Check Replay Status
```bash
curl "http://localhost:8080/api/status" | jq .
# Returns: {"active": true/false, "current_job": {...}}
```

#### Stop Active Replay  
```bash
curl -X POST "http://localhost:8080/api/replay/stop" | jq .
```

#### Monitor Output File
```bash
# Watch the output file in real-time
tail -f logs/output.log

# Count lines written
wc -l logs/output.log

# Check recent entries
tail -n 10 logs/output.log
```

### Output Format

The replay writes logs with timestamps in AAP-compatible format:

```
2024-10-30T17:53:43.087455+00:00 Vault password (gpte_vault_0):
2024-10-30T17:53:43.169160+00:00 [WARNING]: provided hosts list is empty, only localhost is available.
2024-10-30T17:53:43.202858+00:00 PLAY [Step 0000 Setup runtime] *************************************************
2024-10-30T17:53:43.292636+00:00 TASK [debug] *******************************************************************
```

### Troubleshooting Replay

**Common Issues:**

- **"Replay already active"**: Stop current replay first with `/api/replay/stop`
- **"File not found"**: Check file ID with `/api/auto-loaded` or `/api/logs/upload`
- **No output**: Verify permissions on `logs/` directory (`chmod 777 logs/`)
- **OTLP errors**: Ensure endpoint is reachable and accepts logs

**Debug Commands:**
```bash
# Check application logs
docker logs $(docker ps -q) | tail -n 20

# Verify file permissions
ls -la logs/

# Test OTLP endpoint
curl -X POST http://your-otlp-endpoint/v1/logs \
  -H 'Content-Type: application/json' \
  -d '{"test": "connectivity"}'
```

## Integration Examples

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
POD=$(oc get pods -l app.kubernetes.io/name=aap-mock -n aap-mock -o name | head -n1)
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

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Service port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DATA_DIR` | `/data` | Persistent data directory |
| `OUTPUT_LOG_DIR` | `/var/log/aap-mock` | Log output directory |

### Sample Logs Directory

Place `.log` or `.txt` files in `./sample-logs/` directory for auto-loading on startup:

```bash
./sample-logs/                # Empty by default - add your files here
├── your-job-1.log           # Your AAP logs
├── production-deploy.log    # Your AAP logs  
└── your-custom-job.log      # Add your own AAP logs here
```

## Support

### Getting Help

- 📖 **Documentation**: Check this README and inline code docs
- 🐛 **Bug Reports**: [Open an issue](../../issues) with detailed reproduction steps
- 💡 **Feature Requests**: [Open an issue](../../issues) with your use case
- 💬 **Questions**: [Start a discussion](../../discussions)

### Troubleshooting

**Common Issues**:
- **No jobs showing**: Upload a sample AAP log file first
- **Permission errors**: Ensure container has write access to mounted volumes
- **API 404s**: Check that you're using `/api/v2/` paths (not `/api/logs/`)

**Debugging Commands**:
```bash
# Check application logs
oc logs -l app=aap-mock -n aap-mock -f

# Check storage status  
oc get pvc -n aap-mock

# Test API health
curl -s https://HOST/healthz | jq .
```

---

## 🎯 Summary

**True AAP Replacement** - This service provides **100% compatible AAP REST API endpoints** that work identically to real Ansible Automation Platform:

✅ **Drop-in replacement** - Point existing applications here  
✅ **No code changes needed** - Same URLs, same JSON responses  
✅ **Production ready** - Health checks, security, persistent storage  
✅ **OpenShift native** - Helm charts, Routes, proper RBAC  
✅ **Real data support** - Upload actual AAP logs, get real API responses

**Perfect for**: Development environments, testing pipelines, demos, and integration development where real AAP isn't available.

---

<div align="center">
  <strong>⭐ Star this repository if it helps your AAP development workflow! ⭐</strong>
</div>

