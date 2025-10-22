#!/usr/bin/env python3
"""
AAP Log Generator - Mock Ansible Automation Platform logs for testing
"""

import asyncio
import json
import logging
import os
import random
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import threading
import queue

import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path("/data")
UPLOADS_DIR = DATA_DIR / "uploads"
GENERATED_DIR = DATA_DIR / "generated"
OUTPUT_LOG_DIR = Path("/var/log/aap-mock")
OUTPUT_LOG_FILE = OUTPUT_LOG_DIR / "output.log"

# Ensure directories exist
for dir_path in [UPLOADS_DIR, GENERATED_DIR, OUTPUT_LOG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AAP Log Generator",
    description="Mock Ansible Automation Platform logs for testing",
    version="1.0.0"
)

# Global replay state
replay_state = {
    "active": False,
    "stop_event": None,
    "current_job": None
}

# AAP-compatible job storage
aap_jobs_db = {}  # job_id -> job_data
aap_job_events_db = {}  # job_id -> [events]
aap_next_job_id = 1
aap_next_event_id = 1

# Pydantic models
class GenerateLogsRequest(BaseModel):
    job_id: str
    hosts: List[str] = ["host1.example.com", "host2.example.com"]
    tasks: List[str] = ["Setup environment", "Install packages", "Configure services", "Deploy application"]
    duration_minutes: int = 5
    failure_rate: float = 0.1
    events_per_minute: int = 60

class ReplayRequest(BaseModel):
    source: str  # "uploaded" or "generated"
    id_or_path: str
    mode: str = "file"  # "file", "otlp", or "both"
    rate_lines_per_sec: int = 20
    loop: bool = False
    jitter_ms: int = 100
    otlp_endpoint: Optional[str] = None

class UploadResponse(BaseModel):
    id: str
    path: str
    lines_estimate: int
    aap_job_id: Optional[int] = None
    aap_job_url: Optional[str] = None

class StatusResponse(BaseModel):
    active: bool
    current_job: Optional[Dict[str, Any]] = None

# AAP-compatible response models
class AAPJobResponse(BaseModel):
    id: int
    name: str
    status: str
    started: Optional[str] = None
    finished: Optional[str] = None
    elapsed: float
    job_template: int
    inventory: int
    project: int
    playbook: str
    execution_node: str
    created: str
    modified: str
    job_type: str = "run"
    launch_type: str = "manual"
    url: str

class AAPJobEventResponse(BaseModel):
    id: int
    event: str
    counter: int
    event_display: str
    event_data: Dict[str, Any]
    event_level: int
    failed: bool
    changed: bool
    uuid: str
    parent_uuid: Optional[str] = None
    host: Optional[str] = None
    host_name: Optional[str] = None
    playbook: Optional[str] = None
    play: Optional[str] = None
    task: Optional[str] = None
    role: Optional[str] = None
    stdout: str
    start_line: int
    end_line: int
    verbosity: int
    created: str
    modified: str
    url: str

class AAPListResponse(BaseModel):
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[Dict[str, Any]]

# AAP log parsing functions
def parse_aap_log_line(line: str, line_number: int) -> Optional[Dict[str, Any]]:
    """Parse a single AAP log line into job event format"""
    # Pattern: TIMESTAMP LEVEL [job_id:host] MESSAGE
    # or: TIMESTAMP LEVEL [job_id] MESSAGE
    pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)\s+(\w+)\s+\[([^\]]+)\]\s+(.*)'
    match = re.match(pattern, line.strip())
    
    if not match:
        return None
    
    timestamp, level, job_info, message = match.groups()
    
    # Parse job_info: "job_123" or "job_123:web01.example.com"
    if ':' in job_info:
        job_id_str, host = job_info.split(':', 1)
    else:
        job_id_str, host = job_info, None
    
    # Extract job ID number
    job_id_match = re.search(r'job_(\d+)', job_id_str)
    if not job_id_match:
        return None
    
    job_id = int(job_id_match.group(1))
    
    # Determine event type and extract task info
    event_type = "runner_on_ok"
    task_name = None
    event_display = message
    stdout = ""
    failed = level == "ERROR"
    changed = False
    
    if "started" in message.lower():
        event_type = "runner_on_start"
        task_match = re.search(r"TASK \[([^\]]+)\]", message)
        if task_match:
            task_name = task_match.group(1)
    elif "running" in message.lower():
        event_type = "runner_on_start"
        task_match = re.search(r"TASK \[([^\]]+)\]", message)
        if task_match:
            task_name = task_match.group(1)
    elif "completed successfully" in message.lower():
        event_type = "runner_on_ok"
        task_match = re.search(r"TASK \[([^\]]+)\]", message)
        if task_match:
            task_name = task_match.group(1)
        changed = True
    elif "failed" in message.lower():
        event_type = "runner_on_failed"
        task_match = re.search(r"TASK \[([^\]]+)\]", message)
        if task_match:
            task_name = task_match.group(1)
    elif "stdout:" in message:
        event_type = "runner_on_ok"
        stdout = message.replace("stdout:", "").strip()
        event_display = f"STDOUT: {stdout}"
    elif "stderr:" in message:
        event_type = "runner_on_failed"
        stdout = message.replace("stderr:", "").strip()
        event_display = f"STDERR: {stdout}"
        failed = True
    elif "Job" in message and "started" in message:
        event_type = "playbook_on_start"
    elif "Job" in message and "completed" in message:
        event_type = "playbook_on_stats"
    elif "PLAY RECAP" in message:
        event_type = "playbook_on_stats"
        stdout = message
    
    return {
        "job_id": job_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "event_display": event_display,
        "host": host,
        "task": task_name,
        "stdout": stdout,
        "level": level,
        "failed": failed,
        "changed": changed,
        "line_number": line_number,
        "message": message
    }

def create_aap_job_from_log(log_content: str, job_name: str) -> int:
    """Parse log content and create AAP job with events"""
    global aap_next_job_id, aap_next_event_id
    
    lines = log_content.split('\n')
    events = []
    job_id = None
    hosts = set()
    tasks = set()
    start_time = None
    end_time = None
    
    for line_num, line in enumerate(lines, 1):
        if not line.strip():
            continue
        
        event_data = parse_aap_log_line(line, line_num)
        if not event_data:
            continue
        
        if job_id is None:
            job_id = event_data["job_id"]
        
        if event_data["host"]:
            hosts.add(event_data["host"])
        
        if event_data["task"]:
            tasks.add(event_data["task"])
        
        if start_time is None:
            start_time = event_data["timestamp"]
        end_time = event_data["timestamp"]
        
        # Create AAP job event
        event = {
            "id": aap_next_event_id,
            "event": event_data["event_type"],
            "counter": len(events) + 1,
            "event_display": event_data["event_display"],
            "event_data": {
                "res": {"stdout": event_data["stdout"]} if event_data["stdout"] else {},
                "task": event_data["task"],
                "task_args": "",
                "task_action": event_data["task"] if event_data["task"] else "",
                "host": event_data["host"]
            },
            "event_level": 3,
            "failed": event_data["failed"],
            "changed": event_data["changed"],
            "uuid": str(uuid.uuid4()),
            "parent_uuid": None,
            "host": event_data["host"],
            "host_name": event_data["host"],
            "playbook": "main.yml",
            "play": "Deploy Application",
            "task": event_data["task"],
            "role": None,
            "stdout": event_data["stdout"],
            "start_line": event_data["line_number"],
            "end_line": event_data["line_number"],
            "verbosity": 0,
            "created": event_data["timestamp"],
            "modified": event_data["timestamp"],
            "url": f"/api/v2/job_events/{aap_next_event_id}/"
        }
        events.append(event)
        aap_next_event_id += 1
    
    # Calculate elapsed time
    if start_time and end_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        elapsed = (end_dt - start_dt).total_seconds()
    else:
        elapsed = 0.0
    
    # Determine job status
    has_failures = any(e["failed"] for e in events)
    status = "failed" if has_failures else "successful"
    
    # Create AAP job
    job = {
        "id": job_id or aap_next_job_id,
        "name": job_name,
        "status": status,
        "started": start_time,
        "finished": end_time,
        "elapsed": elapsed,
        "job_template": 1,
        "inventory": 1,
        "project": 1,
        "playbook": "main.yml",
        "execution_node": "controller-1",
        "created": start_time or datetime.now(timezone.utc).isoformat(),
        "modified": end_time or datetime.now(timezone.utc).isoformat(),
        "job_type": "run",
        "launch_type": "manual",
        "url": f"/api/v2/jobs/{job_id or aap_next_job_id}/"
    }
    
    final_job_id = job_id or aap_next_job_id
    aap_jobs_db[final_job_id] = job
    aap_job_events_db[final_job_id] = events
    
    if job_id is None:
        aap_next_job_id += 1
    
    return final_job_id

# AAP-compatible API endpoints
@app.get("/api/v2/jobs/")
def list_jobs(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
    """List all jobs (AAP-compatible endpoint)"""
    jobs = list(aap_jobs_db.values())
    total_count = len(jobs)
    
    # Simple pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_jobs = jobs[start_idx:end_idx]
    
    return {
        "count": total_count,
        "next": f"/api/v2/jobs/?page={page + 1}&page_size={page_size}" if end_idx < total_count else None,
        "previous": f"/api/v2/jobs/?page={page - 1}&page_size={page_size}" if page > 1 else None,
        "results": page_jobs
    }

@app.get("/api/v2/jobs/{job_id}/")
def get_job_detail(job_id: int):
    """Get job details (AAP-compatible endpoint)"""
    if job_id not in aap_jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return aap_jobs_db[job_id]

@app.get("/api/v2/jobs/{job_id}/job_events/")
def get_job_events(job_id: int, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    """Get job events (AAP-compatible endpoint)"""
    if job_id not in aap_job_events_db:
        raise HTTPException(status_code=404, detail="Job not found")
    
    events = aap_job_events_db[job_id]
    total_count = len(events)
    
    # Simple pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_events = events[start_idx:end_idx]
    
    return {
        "count": total_count,
        "next": f"/api/v2/jobs/{job_id}/job_events/?page={page + 1}&page_size={page_size}" if end_idx < total_count else None,
        "previous": f"/api/v2/jobs/{job_id}/job_events/?page={page - 1}&page_size={page_size}" if page > 1 else None,
        "results": page_events
    }

@app.get("/api/v2/jobs/{job_id}/stdout/")
def get_job_stdout(job_id: int, format: str = Query("json"), download: bool = Query(False)):
    """Get job stdout (AAP-compatible endpoint)"""
    if job_id not in aap_job_events_db:
        raise HTTPException(status_code=404, detail="Job not found")
    
    events = aap_job_events_db[job_id]
    
    if format == "txt" or format == "ansi":
        # Return plain text stdout
        stdout_lines = []
        for event in events:
            if event.get("stdout"):
                stdout_lines.append(event["stdout"])
            else:
                stdout_lines.append(event["event_display"])
        
        content = "\n".join(stdout_lines)
        return PlainTextResponse(content, media_type="text/plain")
    
    # Return JSON format with range info
    stdout_data = {
        "range": {"start": 0, "end": len(events), "absolute_end": len(events)},
        "content": ""
    }
    
    stdout_lines = []
    for event in events:
        if event.get("stdout"):
            stdout_lines.append(event["stdout"])
        else:
            stdout_lines.append(event["event_display"])
    
    stdout_data["content"] = "\n".join(stdout_lines)
    
    return stdout_data

@app.get("/api/v2/job_events/{event_id}/")
def get_job_event_detail(event_id: int):
    """Get specific job event details (AAP-compatible endpoint)"""
    # Search through all job events
    for job_id, events in aap_job_events_db.items():
        for event in events:
            if event["id"] == event_id:
                return event
    
    raise HTTPException(status_code=404, detail="Job event not found")

# Additional AAP resource endpoints for compatibility
@app.get("/api/v2/job_templates/")
def list_job_templates():
    """List job templates (AAP-compatible endpoint)"""
    templates = [
        {
            "id": 1,
            "name": "Deploy Application",
            "description": "Deploy application playbook",
            "job_type": "run",
            "inventory": 1,
            "project": 1,
            "playbook": "main.yml",
            "created": "2024-01-01T00:00:00.000000Z",
            "modified": "2024-01-01T00:00:00.000000Z",
            "url": "/api/v2/job_templates/1/"
        }
    ]
    return {
        "count": len(templates),
        "next": None,
        "previous": None,
        "results": templates
    }

@app.get("/api/v2/inventories/")
def list_inventories():
    """List inventories (AAP-compatible endpoint)"""
    inventories = [
        {
            "id": 1,
            "name": "Production Hosts",
            "description": "Production environment inventory",
            "organization": 1,
            "kind": "",
            "host_filter": None,
            "variables": "{}",
            "created": "2024-01-01T00:00:00.000000Z",
            "modified": "2024-01-01T00:00:00.000000Z",
            "url": "/api/v2/inventories/1/"
        }
    ]
    return {
        "count": len(inventories),
        "next": None,
        "previous": None,
        "results": inventories
    }

@app.get("/api/v2/projects/")
def list_projects():
    """List projects (AAP-compatible endpoint)"""
    projects = [
        {
            "id": 1,
            "name": "Application Deployment",
            "description": "Main application deployment project",
            "local_path": "",
            "scm_type": "git",
            "scm_url": "https://github.com/example/ansible-playbooks.git",
            "scm_branch": "main",
            "status": "successful",
            "created": "2024-01-01T00:00:00.000000Z",
            "modified": "2024-01-01T00:00:00.000000Z",
            "url": "/api/v2/projects/1/"
        }
    ]
    return {
        "count": len(projects),
        "next": None,
        "previous": None,
        "results": projects
    }

@app.get("/api/v2/")
def api_root():
    """AAP API root endpoint"""
    return {
        "description": "AAP Mock API v2",
        "current_version": "/api/v2/",
        "available_versions": {
            "v2": "/api/v2/"
        },
        "oauth2": "/api/o/",
        "jobs": "/api/v2/jobs/",
        "job_templates": "/api/v2/job_templates/",
        "inventories": "/api/v2/inventories/",
        "projects": "/api/v2/projects/",
        "job_events": "/api/v2/job_events/"
    }

# Health checks
@app.get("/healthz")
def health_check():
    return {"status": "healthy"}

@app.get("/readyz")
def readiness_check():
    return {"status": "ready"}

@app.get("/api/status")
def get_status() -> StatusResponse:
    """Get current replay status"""
    return StatusResponse(
        active=replay_state["active"],
        current_job=replay_state["current_job"]
    )

@app.post("/api/logs/upload")
async def upload_log(file: UploadFile = File(...)) -> UploadResponse:
    """Upload a log file for later replay and create AAP job"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Generate unique ID and save file
    file_id = str(uuid.uuid4())
    file_path = UPLOADS_DIR / f"{file_id}.log"
    
    content = await file.read()
    content_str = content.decode('utf-8', errors='ignore')
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Estimate line count
    lines_estimate = content_str.count('\n')
    
    # Parse into AAP job format
    try:
        job_id = create_aap_job_from_log(content_str, file.filename or f"Uploaded Job {file_id}")
        logger.info(f"Uploaded file {file.filename} as {file_id}, created AAP job {job_id}, estimated {lines_estimate} lines")
    except Exception as e:
        logger.warning(f"Failed to parse uploaded file as AAP job: {e}")
        job_id = None
    
    response = UploadResponse(
        id=file_id,
        path=str(file_path),
        lines_estimate=lines_estimate
    )
    
    # Add AAP job info if successfully parsed
    if job_id:
        response.aap_job_id = job_id
        response.aap_job_url = f"/api/v2/jobs/{job_id}/"
    
    return response

@app.post("/api/logs/generate")
def generate_logs(request: GenerateLogsRequest):
    """Generate synthetic AAP logs"""
    job_id = request.job_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = GENERATED_DIR / f"{job_id}_{timestamp}.jsonl"
    
    # Generate synthetic logs
    logs = _generate_synthetic_logs(request)
    
    # Write to file
    with open(output_path, "w") as f:
        for log_entry in logs:
            f.write(json.dumps(log_entry) + "\n")
    
    logger.info(f"Generated {len(logs)} log entries for job {job_id}")
    
    return {
        "job_id": job_id,
        "path": str(output_path),
        "entries_generated": len(logs),
        "estimated_duration": request.duration_minutes
    }

@app.post("/api/logs/replay")
def start_replay(request: ReplayRequest, background_tasks: BackgroundTasks):
    """Start replaying logs"""
    if replay_state["active"]:
        raise HTTPException(status_code=409, detail="Replay already active")
    
    # Find source file
    if request.source == "uploaded":
        source_path = UPLOADS_DIR / f"{request.id_or_path}.log"
    elif request.source == "generated":
        if request.id_or_path.endswith('.jsonl'):
            source_path = GENERATED_DIR / request.id_or_path
        else:
            # Find generated file by job_id pattern
            candidates = list(GENERATED_DIR.glob(f"{request.id_or_path}_*.jsonl"))
            if not candidates:
                raise HTTPException(status_code=404, detail="Generated log file not found")
            source_path = max(candidates, key=lambda p: p.stat().st_mtime)  # Most recent
    else:
        raise HTTPException(status_code=400, detail="Source must be 'uploaded' or 'generated'")
    
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    # Set up replay state
    stop_event = threading.Event()
    replay_state["active"] = True
    replay_state["stop_event"] = stop_event
    replay_state["current_job"] = {
        "source": request.source,
        "path": str(source_path),
        "mode": request.mode,
        "rate": request.rate_lines_per_sec,
        "loop": request.loop,
        "started_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Start replay in background
    background_tasks.add_task(_replay_logs, source_path, request, stop_event)
    
    return {"status": "started", "source_path": str(source_path)}

@app.post("/api/replay/stop")
def stop_replay():
    """Stop active replay"""
    if not replay_state["active"]:
        raise HTTPException(status_code=400, detail="No active replay")
    
    if replay_state["stop_event"]:
        replay_state["stop_event"].set()
    
    return {"status": "stopping"}

def _generate_synthetic_logs(request: GenerateLogsRequest) -> List[Dict[str, Any]]:
    """Generate synthetic AAP-style logs"""
    logs = []
    start_time = datetime.now(timezone.utc)
    
    # Job start event
    logs.append({
        "timestamp": start_time.isoformat(),
        "job_id": request.job_id,
        "event": "job_start",
        "message": f"Job {request.job_id} started",
        "level": "INFO"
    })
    
    events_per_minute = request.events_per_minute
    total_events = request.duration_minutes * events_per_minute
    time_increment = 60.0 / events_per_minute  # seconds between events
    
    current_time = start_time
    
    for i in range(total_events):
        # Advance time
        current_time = start_time.replace(
            second=int(start_time.second + (i * time_increment)) % 60,
            minute=start_time.minute + int((start_time.second + (i * time_increment)) / 60)
        )
        
        # Pick random host and task
        host = random.choice(request.hosts)
        task = random.choice(request.tasks)
        
        # Determine if this should be a failure
        is_failure = random.random() < request.failure_rate
        
        # Generate different types of events
        event_types = ["task_start", "task_running", "task_result"]
        event_type = random.choice(event_types)
        
        log_entry = {
            "timestamp": current_time.isoformat(),
            "job_id": request.job_id,
            "host": host,
            "task": task,
            "event": event_type,
            "level": "ERROR" if is_failure else "INFO"
        }
        
        if event_type == "task_start":
            log_entry["message"] = f"Starting task '{task}' on {host}"
        elif event_type == "task_running":
            log_entry["message"] = f"Executing task '{task}' on {host}"
        elif event_type == "task_result":
            if is_failure:
                log_entry["message"] = f"Task '{task}' failed on {host}: Connection timeout"
                log_entry["status"] = "failed"
            else:
                log_entry["message"] = f"Task '{task}' completed successfully on {host}"
                log_entry["status"] = "ok"
        
        logs.append(log_entry)
    
    # Job end event
    end_time = current_time
    logs.append({
        "timestamp": end_time.isoformat(),
        "job_id": request.job_id,
        "event": "job_end",
        "message": f"Job {request.job_id} completed",
        "level": "INFO",
        "duration": f"{request.duration_minutes}m"
    })
    
    return logs

def _replay_logs(source_path: Path, request: ReplayRequest, stop_event: threading.Event):
    """Replay logs from file"""
    try:
        logger.info(f"Starting replay from {source_path}")
        
        while True:
            with open(source_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    if stop_event.is_set():
                        logger.info("Replay stopped by user")
                        return
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Add jitter
                    if request.jitter_ms > 0:
                        jitter = random.uniform(0, request.jitter_ms / 1000.0)
                        time.sleep(jitter)
                    
                    # Output to file
                    if request.mode in ["file", "both"]:
                        _write_to_output_file(line)
                    
                    # Output to OTLP
                    if request.mode in ["otlp", "both"] and request.otlp_endpoint:
                        _send_to_otlp(line, request.otlp_endpoint)
                    
                    # Rate limiting
                    if request.rate_lines_per_sec > 0:
                        time.sleep(1.0 / request.rate_lines_per_sec)
            
            if not request.loop:
                break
            
            logger.info("Looping replay...")
    
    except Exception as e:
        logger.error(f"Error during replay: {e}")
    finally:
        replay_state["active"] = False
        replay_state["current_job"] = None
        logger.info("Replay completed")

def _write_to_output_file(line: str):
    """Write log line to output file"""
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(OUTPUT_LOG_FILE, "a") as f:
        f.write(f"{timestamp} {line}\n")

def _send_to_otlp(line: str, endpoint: str):
    """Send log line to OTLP endpoint"""
    try:
        # Simple OTLP HTTP JSON format
        payload = {
            "resourceLogs": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "aap-mock"}}
                    ]
                },
                "scopeLogs": [{
                    "scope": {"name": "aap-mock"},
                    "logRecords": [{
                        "timeUnixNano": str(int(time.time() * 1e9)),
                        "body": {"stringValue": line},
                        "attributes": [
                            {"key": "source", "value": {"stringValue": "aap-mock"}}
                        ]
                    }]
                }]
            }]
        }
        
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        response.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to send to OTLP: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

