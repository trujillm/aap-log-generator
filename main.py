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
# Application logs → file (for debugging/troubleshooting)
# AAP mock logs → stdout (for Alloy/Promtail collection)

# Application logger - writes to file + stdout
app_logger = logging.getLogger(__name__)
app_logger.setLevel(logging.INFO)

# Try to add file handler for application logs (optional - may fail locally)
try:
    app_log_handler = logging.FileHandler('/var/log/aap-mock/app.log')
    app_log_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    app_logger.addHandler(app_log_handler)
except (PermissionError, FileNotFoundError):
    # If file logging fails, just use stdout (common for local development)
    pass

# Console handler for application logs (always available)
app_console_handler = logging.StreamHandler()
app_console_handler.setFormatter(logging.Formatter(
    '[APP] %(asctime)s - %(levelname)s - %(message)s'
))
app_logger.addHandler(app_console_handler)

# AAP mock logger - writes ONLY to stdout (Kubernetes captures this)
aap_logger = logging.getLogger('aap_mock')
aap_logger.setLevel(logging.INFO)
aap_logger.propagate = False  # Don't propagate to root logger

# Stdout handler for AAP mock logs (what Alloy collects)
aap_stdout_handler = logging.StreamHandler()
aap_stdout_handler.setFormatter(logging.Formatter('%(message)s'))  # Raw format - already structured
aap_logger.addHandler(aap_stdout_handler)

# For backward compatibility with existing code
logger = app_logger

# Configuration
DATA_DIR = Path("/data")
UPLOADS_DIR = DATA_DIR / "uploads"
GENERATED_DIR = DATA_DIR / "generated"
AUTO_LOAD_DIR = Path("/app/sample-logs")  # New: auto-load directory
OUTPUT_LOG_DIR = Path("/var/log/aap-mock")
OUTPUT_LOG_FILE = OUTPUT_LOG_DIR / "output.log"

# Ensure directories exist
for dir_path in [UPLOADS_DIR, GENERATED_DIR, AUTO_LOAD_DIR, OUTPUT_LOG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AAP Log Generator",
    description="Mock Ansible Automation Platform logs for testing",
    version="1.0.0"
)

# Global replay state and stop mechanism
replay_state = {
    "active": False,
    "stop_event": None,
    "current_job": None
}

# CRITICAL FIX: Global stop flag that persists even when state gets corrupted
global_stop_flag = threading.Event()  # This persists across state resets

# AAP-compatible job storage
aap_jobs_db = {}  # job_id -> job_data
aap_job_events_db = {}  # job_id -> [events]
aap_next_job_id = 1
aap_next_event_id = 1

# Auto-loaded files storage
auto_loaded_files = {}  # filename -> file_path

# Pydantic models
class GenerateLogsRequest(BaseModel):
    job_id: str
    hosts: List[str] = ["host1.example.com", "host2.example.com"]
    tasks: List[str] = ["Setup environment", "Install packages", "Configure services", "Deploy application"]
    duration_minutes: int = 5
    failure_rate: float = 0.1
    events_per_minute: int = 60

class ReplayRequest(BaseModel):
    source: str  # "uploaded", "generated", or "auto-loaded"
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

def auto_load_sample_logs():
    """Auto-load log files from the sample-logs directory on startup"""
    if not AUTO_LOAD_DIR.exists():
        logger.info(f"Auto-load directory {AUTO_LOAD_DIR} does not exist, skipping auto-load")
        return
    
    # Supported file extensions
    supported_extensions = {'.log', '.txt'}
    loaded_count = 0
    skipped_count = 0
    
    logger.info(f"🔍 Scanning {AUTO_LOAD_DIR} for log files to auto-load...")
    
    for file_path in AUTO_LOAD_DIR.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            try:
                # Check file size first
                file_size = file_path.stat().st_size
                if file_size == 0:
                    logger.warning(f"⚠️  Skipping empty file: {file_path.name} (0 bytes)")
                    skipped_count += 1
                    continue
                
                # Read file content
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Check for meaningful content (not just whitespace)
                if not content.strip():
                    logger.warning(f"⚠️  Skipping file with only whitespace: {file_path.name}")
                    skipped_count += 1
                    continue
                
                # Count actual lines with content
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                if len(lines) == 0:
                    logger.warning(f"⚠️  Skipping file with no content lines: {file_path.name}")
                    skipped_count += 1
                    continue
                
                # Use filename without extension as the key
                filename_key = file_path.stem
                
                # Store in auto-loaded files registry
                auto_loaded_files[filename_key] = str(file_path)
                
                # Parse into AAP job format
                job_id = create_aap_job_from_log(content, file_path.name)
                
                logger.info(f"✅ Auto-loaded: {file_path.name} → AAP job {job_id} (key: {filename_key}) - {len(lines)} lines")
                loaded_count += 1
                
            except Exception as e:
                logger.warning(f"❌ Failed to auto-load {file_path.name}: {e}")
                skipped_count += 1
    
    # Summary report
    if loaded_count > 0:
        logger.info(f"🎉 Successfully auto-loaded {loaded_count} log files")
        logger.info(f"📋 Available for replay: {list(auto_loaded_files.keys())}")
    else:
        logger.info("📂 No valid log files found in sample-logs directory")
    
    if skipped_count > 0:
        logger.info(f"⚠️  Skipped {skipped_count} invalid/empty files")
        
    if loaded_count == 0 and skipped_count == 0:
        logger.info(f"💡 Drop .log or .txt files in {AUTO_LOAD_DIR} to auto-load them!")

# AAP log parsing functions
def parse_aap_log_line(line: str, line_number: int) -> Optional[Dict[str, Any]]:
    """Parse a single AAP log line into job event format - supports multiple formats"""
    line = line.strip()
    if not line:
        return None
    
    # Try multiple AAP log format patterns
    parsers = [
        _parse_structured_format,    # Our current format: TIMESTAMP LEVEL [job_id:host] MESSAGE  
        _parse_json_format,          # AAP JSON event logs: {"event": "runner_on_start", ...}
        _parse_ansible_output,       # Raw ansible output: "TASK [setup] ***", "ok: [host]"
        _parse_aap_system_logs,      # AAP system logs: "2024-01-15 10:30:00 INFO Job started"
        _parse_awx_logs             # AWX/Tower logs: various formats
    ]
    
    for parser in parsers:
        try:
            result = parser(line, line_number)
            if result:
                return result
        except Exception as e:
            logger.debug(f"Parser {parser.__name__} failed for line {line_number}: {e}")
            continue
    
    # If no parser worked, create a generic log entry
    logger.debug(f"No parser matched line {line_number}: {line[:100]}...")
    return _create_generic_entry(line, line_number)

def _parse_structured_format(line: str, line_number: int) -> Optional[Dict[str, Any]]:
    """Parse our current structured format: TIMESTAMP LEVEL [job_id:host] MESSAGE"""
    pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)\s+(\w+)\s+\[([^\]]+)\]\s+(.*)'
    match = re.match(pattern, line)
    
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

def _parse_json_format(line: str, line_number: int) -> Optional[Dict[str, Any]]:
    """Parse AAP JSON event logs: {"event": "runner_on_start", "counter": 1, ...}"""
    try:
        if not line.startswith('{'):
            return None
        
        data = json.loads(line)
        
        # Extract job ID from various possible fields
        job_id = data.get('job_id') or data.get('job') or 1
        if isinstance(job_id, str) and job_id.startswith('job_'):
            job_id = int(job_id.replace('job_', ''))
        elif isinstance(job_id, str) and job_id.isdigit():
            job_id = int(job_id)
        elif not isinstance(job_id, int):
            job_id = 1
        
        return {
            "job_id": job_id,
            "timestamp": data.get('created') or data.get('timestamp') or datetime.now(timezone.utc).isoformat(),
            "event_type": data.get('event', 'runner_on_ok'),
            "event_display": data.get('event_display') or data.get('stdout', ''),
            "host": data.get('host') or data.get('host_name'),
            "task": data.get('task'),
            "stdout": data.get('stdout', ''),
            "level": "ERROR" if data.get('failed') else "INFO",
            "failed": data.get('failed', False),
            "changed": data.get('changed', False),
            "line_number": line_number,
            "message": data.get('event_display') or str(data)
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return None

def _parse_ansible_output(line: str, line_number: int) -> Optional[Dict[str, Any]]:
    """Parse raw ansible playbook output"""
    
    # PLAY header
    if line.startswith('PLAY ['):
        play_match = re.match(r'PLAY \[([^\]]+)\]', line)
        play_name = play_match.group(1) if play_match else "Unknown Play"
        return {
            "job_id": 1,  # Default job ID
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "playbook_on_play_start",
            "event_display": f"PLAY [{play_name}]",
            "host": None,
            "task": None,
            "stdout": line,
            "level": "INFO",
            "failed": False,
            "changed": False,
            "line_number": line_number,
            "message": line
        }
    
    # TASK header
    elif line.startswith('TASK ['):
        task_match = re.match(r'TASK \[([^\]]+)\]', line)
        task_name = task_match.group(1) if task_match else "Unknown Task"
        return {
            "job_id": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "runner_on_start",
            "event_display": f"TASK [{task_name}]",
            "host": None,
            "task": task_name,
            "stdout": line,
            "level": "INFO",
            "failed": False,
            "changed": False,
            "line_number": line_number,
            "message": line
        }
    
    # Task results: ok: [host], changed: [host], failed: [host]
    elif re.match(r'^(ok|changed|failed|fatal|unreachable|skipping):\s*\[([^\]]+)\]', line):
        result_match = re.match(r'^(ok|changed|failed|fatal|unreachable|skipping):\s*\[([^\]]+)\](.*)', line)
        if result_match:
            status, host, extra = result_match.groups()
            
            event_type = "runner_on_ok"
            if status in ["changed"]:
                event_type = "runner_on_ok"
                changed = True
            elif status in ["failed", "fatal"]:
                event_type = "runner_on_failed"
                changed = False
            elif status == "unreachable":
                event_type = "runner_on_unreachable"
                changed = False
            elif status == "skipping":
                event_type = "runner_on_skipped"
                changed = False
            else:
                changed = False
            
            return {
                "job_id": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "event_display": line,
                "host": host,
                "task": None,
                "stdout": extra.strip() if extra else "",
                "level": "ERROR" if status in ["failed", "fatal"] else "INFO",
                "failed": status in ["failed", "fatal"],
                "changed": changed,
                "line_number": line_number,
                "message": line
            }
    
    return None

def _parse_aap_system_logs(line: str, line_number: int) -> Optional[Dict[str, Any]]:
    """Parse AAP system logs: 2024-01-15 10:30:00 INFO Job 123 started"""
    
    # Pattern: YYYY-MM-DD HH:MM:SS LEVEL MESSAGE
    pattern = r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})[,.]?\d*\s+(\w+)\s+(.*)'
    match = re.match(pattern, line)
    
    if not match:
        return None
    
    timestamp_str, level, message = match.groups()
    
    # Convert timestamp to ISO format
    try:
        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        dt = dt.replace(tzinfo=timezone.utc)
        timestamp = dt.isoformat()
    except ValueError:
        timestamp = datetime.now(timezone.utc).isoformat()
    
    # Extract job ID if present
    job_id = 1
    job_match = re.search(r'[Jj]ob\s+(\d+)', message)
    if job_match:
        job_id = int(job_match.group(1))
    
    # Extract host if present
    host = None
    host_patterns = [
        r'\[([a-zA-Z0-9.-]+)\]',  # [hostname]
        r'host[:\s]+([a-zA-Z0-9.-]+)',  # host: hostname
        r'on\s+([a-zA-Z0-9.-]+)'  # on hostname
    ]
    for pattern in host_patterns:
        host_match = re.search(pattern, message)
        if host_match:
            potential_host = host_match.group(1)
            # Simple check if it looks like a hostname
            if '.' in potential_host or len(potential_host) > 3:
                host = potential_host
                break
    
    # Determine event type
    event_type = "runner_on_ok"
    failed = level.upper() in ["ERROR", "FATAL", "CRITICAL"]
    changed = "changed" in message.lower() or "updated" in message.lower()
    
    if "start" in message.lower():
        event_type = "runner_on_start"
    elif "complete" in message.lower() or "finish" in message.lower():
        event_type = "runner_on_ok"
    elif "fail" in message.lower() or "error" in message.lower():
        event_type = "runner_on_failed"
    
    return {
        "job_id": job_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "event_display": message,
        "host": host,
        "task": None,
        "stdout": "",
        "level": level.upper(),
        "failed": failed,
        "changed": changed,
        "line_number": line_number,
        "message": message
    }

def _parse_awx_logs(line: str, line_number: int) -> Optional[Dict[str, Any]]:
    """Parse AWX/Tower specific log formats"""
    
    # AWX supervisor logs: Jan 15 10:30:00 tower-01 awx-manage[1234]: ...
    syslog_pattern = r'(\w+\s+\d+\s+\d{2}:\d{2}:\d{2})\s+([^\s]+)\s+([^:]+):\s*(.*)'
    match = re.match(syslog_pattern, line)
    
    if match:
        timestamp_str, hostname, process, message = match.groups()
        
        # Convert syslog timestamp (add current year)
        try:
            current_year = datetime.now().year
            dt = datetime.strptime(f"{current_year} {timestamp_str}", '%Y %b %d %H:%M:%S')
            dt = dt.replace(tzinfo=timezone.utc)
            timestamp = dt.isoformat()
        except ValueError:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        # Extract job information
        job_id = 1
        job_match = re.search(r'[Jj]ob\s*[:#]?\s*(\d+)', message)
        if job_match:
            job_id = int(job_match.group(1))
        
        level = "INFO"
        if any(word in message.upper() for word in ["ERROR", "FAIL", "FATAL"]):
            level = "ERROR"
        elif any(word in message.upper() for word in ["WARN", "WARNING"]):
            level = "WARN"
        
        return {
            "job_id": job_id,
            "timestamp": timestamp,
            "event_type": "runner_on_ok",
            "event_display": message,
            "host": hostname,
            "task": None,
            "stdout": "",
            "level": level,
            "failed": level == "ERROR",
            "changed": False,
            "line_number": line_number,
            "message": message
        }
    
    return None

def _create_generic_entry(line: str, line_number: int) -> Dict[str, Any]:
    """Create a generic log entry when no specific parser matches"""
    
    # Try to extract some basic information
    level = "INFO"
    if any(word in line.upper() for word in ["ERROR", "FAIL", "FATAL"]):
        level = "ERROR"
    elif any(word in line.upper() for word in ["WARN", "WARNING"]):
        level = "WARN"
    elif any(word in line.upper() for word in ["DEBUG"]):
        level = "DEBUG"
    
    return {
        "job_id": 1,  # Default job ID
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "runner_on_ok",
        "event_display": line,
        "host": None,
        "task": None,
        "stdout": "",
        "level": level,
        "failed": level == "ERROR",
        "changed": False,
        "line_number": line_number,
        "message": line
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

@app.get("/api/auto-loaded")
def list_auto_loaded_files():
    """List available auto-loaded log files"""
    return {
        "count": len(auto_loaded_files),
        "files": [
            {
                "key": key,
                "path": path,
                "filename": Path(path).name
            }
            for key, path in auto_loaded_files.items()
        ]
    }

@app.post("/api/auto-loaded/refresh")
def refresh_auto_loaded_files():
    """Re-scan sample-logs directory and refresh auto-loaded files"""
    logger.info("🔄 Manual refresh of auto-loaded files requested")
    
    # Store previous state for comparison
    previous_files = set(auto_loaded_files.keys())
    previous_count = len(auto_loaded_files)
    
    # Clear current auto-loaded files
    auto_loaded_files.clear()
    
    # Re-run the auto-load process
    auto_load_sample_logs()
    
    # Calculate changes
    current_files = set(auto_loaded_files.keys())
    added_files = current_files - previous_files
    removed_files = previous_files - current_files
    current_count = len(auto_loaded_files)
    
    logger.info(f"📊 Refresh completed: {previous_count} → {current_count} files")
    if added_files:
        logger.info(f"➕ Added: {list(added_files)}")
    if removed_files:
        logger.info(f"➖ Removed: {list(removed_files)}")
    
    return {
        "status": "refreshed",
        "previous_count": previous_count,
        "current_count": current_count,
        "changes": {
            "added": list(added_files),
            "removed": list(removed_files)
        },
        "files": [
            {
                "key": key,
                "path": path,
                "filename": Path(path).name
            }
            for key, path in auto_loaded_files.items()
        ]
    }

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
    # CRITICAL FIX: Force stop any existing replay before starting new one
    if replay_state["active"] and replay_state["stop_event"]:
        logger.warning("🛑 Forcing stop of existing replay before starting new one")
        replay_state["stop_event"].set()
        # Wait a moment for the old task to clean up
        time.sleep(0.5)
    
    # Set up replay state early (needed for "all" functionality)  
    stop_event = threading.Event()
    replay_state["active"] = True
    replay_state["stop_event"] = stop_event
    
    # CRITICAL FIX: Clear global stop flag for new replay
    global_stop_flag.clear()
    
    # Find source file
    if request.source == "uploaded":
        if request.id_or_path == "latest":
            # Find the most recently uploaded file
            uploaded_files = list(UPLOADS_DIR.glob("*.log"))
            if not uploaded_files:
                replay_state["active"] = False  # Reset state on error
                raise HTTPException(status_code=404, detail="No uploaded files found")
            source_path = max(uploaded_files, key=lambda p: p.stat().st_mtime)
            logger.info(f"Using latest uploaded file: {source_path.name}")
        elif request.id_or_path == "all":
            # Special case: replay all uploaded files sequentially
            uploaded_files = list(UPLOADS_DIR.glob("*.log"))
            if not uploaded_files:
                replay_state["active"] = False  # Reset state on error
                raise HTTPException(status_code=404, detail="No uploaded files found")
            
            # Set up current job info for "all" replay
            replay_state["current_job"] = {
                "source": request.source,
                "path": "all_uploaded_files",
                "mode": request.mode,
                "rate": request.rate_lines_per_sec,
                "loop": request.loop,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "files_count": len(uploaded_files),
                "files": [f.name for f in uploaded_files]
            }
            
            # Start background task to replay all files
            background_tasks.add_task(_replay_all_uploaded, request, stop_event)
            
            return {
                "status": "started", 
                "source_path": "all_uploaded_files",
                "files_count": len(uploaded_files),
                "files": [f.name for f in uploaded_files]
            }
        else:
            source_path = UPLOADS_DIR / f"{request.id_or_path}.log"
    elif request.source == "generated":
        if request.id_or_path.endswith('.jsonl'):
            source_path = GENERATED_DIR / request.id_or_path
        else:
            # Find generated file by job_id pattern
            candidates = list(GENERATED_DIR.glob(f"{request.id_or_path}_*.jsonl"))
            if not candidates:
                replay_state["active"] = False  # Reset state on error
                raise HTTPException(status_code=404, detail="Generated log file not found")
            source_path = max(candidates, key=lambda p: p.stat().st_mtime)  # Most recent
    elif request.source == "auto-loaded":
        if request.id_or_path == "all":
            # Special case: replay all auto-loaded files sequentially
            if not auto_loaded_files:
                replay_state["active"] = False  # Reset state on error
                raise HTTPException(status_code=404, detail="No auto-loaded files found")
            
            # Set up current job info for "all" replay
            replay_state["current_job"] = {
                "source": request.source,
                "path": "all_auto_loaded_files",
                "mode": request.mode,
                "rate": request.rate_lines_per_sec,
                "loop": request.loop,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "files_count": len(auto_loaded_files),
                "files": list(auto_loaded_files.keys())
            }
            
            # Start background task to replay all files
            background_tasks.add_task(_replay_all_auto_loaded, request, stop_event)
            
            return {
                "status": "started", 
                "source_path": "all_auto_loaded_files",
                "files_count": len(auto_loaded_files),
                "files": list(auto_loaded_files.keys())
            }
        else:
            # Look up auto-loaded file by filename key
            if request.id_or_path not in auto_loaded_files:
                available_files = list(auto_loaded_files.keys())
                replay_state["active"] = False  # Reset state on error
                raise HTTPException(
                    status_code=404, 
                    detail=f"Auto-loaded file '{request.id_or_path}' not found. Available files: {available_files}"
                )
            source_path = Path(auto_loaded_files[request.id_or_path])
    else:
        replay_state["active"] = False  # Reset state on error
        raise HTTPException(status_code=400, detail="Source must be 'uploaded', 'generated', or 'auto-loaded'")
    
    if not source_path.exists():
        replay_state["active"] = False  # Reset state on error
        raise HTTPException(status_code=404, detail="Log file not found")
    
    # Set up current job info
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
    logger.info(f"🛑 Stop request received. Active: {replay_state['active']}, Stop event exists: {replay_state['stop_event'] is not None}")
    
    # CRITICAL FIX: ALWAYS set global stop flag regardless of state
    logger.info("🛑 Setting global stop flag (works even with corrupted state)")
    global_stop_flag.set()
    
    # Also set regular stop event if it exists
    if replay_state["stop_event"]:
        logger.info("🛑 Setting regular stop event")
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
        
        # Pre-validate file has content to prevent infinite loop
        file_size = source_path.stat().st_size
        if file_size == 0:
            logger.error(f"❌ Cannot replay empty file: {source_path.name} (0 bytes)")
            return
        
        # Count actual content lines
        with open(source_path, 'r') as f:
            content_lines = [line.strip() for line in f if line.strip()]
        
        if len(content_lines) == 0:
            logger.error(f"❌ Cannot replay file with no content: {source_path.name} (no valid lines)")
            return
            
        logger.info(f"📋 File validated: {source_path.name} - {len(content_lines)} lines to replay")
        
        loop_count = 0
        while True:
            if stop_event.is_set() or global_stop_flag.is_set():
                logger.info("🛑 Replay stopped by user (cycle check)")
                return
                
            loop_count += 1
            lines_processed = 0
            
            with open(source_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    if stop_event.is_set() or global_stop_flag.is_set():
                        logger.info("🛑 Replay stopped by user (line check)")
                        return
                    
                    line = line.rstrip('\n\r')  # Only remove newlines, preserve spaces!
                    if not line:
                        continue
                    
                    lines_processed += 1
                    
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
            
            logger.info(f"Completed replay cycle {loop_count}: processed {lines_processed} lines from {source_path.name}")
            
            # Check for stop before deciding to loop
            if stop_event.is_set() or global_stop_flag.is_set():
                logger.info("🛑 Replay stopped by user (before loop decision)")
                return
            
            if not request.loop:
                break
            
            logger.info(f"🔄 Looping replay of {source_path.name}...")
    
    except Exception as e:
        logger.error(f"Error during replay: {e}")
    finally:
        # CRITICAL FIX: Always clean up state, even on exceptions
        replay_state["active"] = False
        replay_state["current_job"] = None
        replay_state["stop_event"] = None
        logger.info("Replay completed and state cleaned up")

def _write_to_output_file(line: str):
    """Write log line to stdout for Kubernetes log collection (Alloy/Promtail)"""
    # Convert any format to structured AAP format for log aggregation
    structured_line = _normalize_to_structured_aap_format(line)
    
    # PRIMARY: Write to stdout for Kubernetes/Alloy collection
    aap_logger.info(structured_line)
    
    # OPTIONAL: Also write to file for backward compatibility / local debugging
    # You can disable this in production if you only want stdout
    with open(OUTPUT_LOG_FILE, "a") as f:
        f.write(f"{structured_line}\n")

def _normalize_to_structured_aap_format(line: str) -> str:
    """Convert any log format to structured AAP format for external log aggregation"""
    # If already in structured format, return as-is
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*?INFO|ERROR|WARN|DEBUG.*?\[.*?\]', line):
        return line
    
    # Get current timestamp in AAP format
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    
    # Determine log level and job context
    level = "INFO"
    job_context = "[aap_mock]"
    
    if any(keyword in line.lower() for keyword in ["error", "failed", "fatal"]):
        level = "ERROR"
    elif any(keyword in line.lower() for keyword in ["warn", "warning"]):
        level = "WARN"
    
    # For raw Ansible output, preserve the content but structure it
    if line.startswith(("PLAY [", "TASK [", "HANDLER [")):
        return f"{timestamp} {level} {job_context} {line}"
    elif line.startswith(("ok:", "changed:", "failed:", "skipping:")):
        return f"{timestamp} {level} {job_context} {line}"
    elif line.startswith("[WARNING]"):
        return f"{timestamp} WARN {job_context} {line}"
    else:
        # Generic structured format
        return f"{timestamp} {level} {job_context} {line}"

def _replay_all_auto_loaded(request: ReplayRequest, stop_event: threading.Event):
    """Replay all auto-loaded files sequentially"""
    try:
        files_to_replay = list(auto_loaded_files.items())
        total_files = len(files_to_replay)
        cycle_count = 0
        
        logger.info(f"Starting replay of all {total_files} auto-loaded files with loop={request.loop}")
        
        # Handle looping at the "all files" level, not individual file level
        while True:
            if stop_event.is_set() or global_stop_flag.is_set():
                logger.info("🛑 Replay all stopped by user (outer loop)")
                return
                
            cycle_count += 1
            replayed_count = 0
            skipped_count = 0
            
            logger.info(f"🔄 Starting cycle {cycle_count} of all files")
            
            for file_index, (file_key, file_path) in enumerate(files_to_replay, 1):
                if stop_event.is_set() or global_stop_flag.is_set():
                    logger.info("🛑 Replay all stopped by user (file loop)")
                    return
                    
                logger.info(f"Processing file {file_index}/{total_files}: {file_key} (cycle {cycle_count})")
                
                # Update current job info to show progress
                if replay_state["current_job"]:
                    replay_state["current_job"]["current_file"] = file_key
                    replay_state["current_job"]["progress"] = f"{file_index}/{total_files}"
                    replay_state["current_job"]["cycle"] = cycle_count
                
                # Pre-validate file before attempting replay
                source_path = Path(file_path)
                
                try:
                    file_size = source_path.stat().st_size
                    if file_size == 0:
                        logger.warning(f"⚠️  Skipping empty file: {file_key} (0 bytes)")
                        skipped_count += 1
                        continue
                    
                    # Quick content check
                    with open(source_path, 'r') as f:
                        content_lines = [line.strip() for line in f if line.strip()]
                    
                    if len(content_lines) == 0:
                        logger.warning(f"⚠️  Skipping file with no content: {file_key} (no valid lines)")
                        skipped_count += 1
                        continue
                    
                    # Create a modified request with loop=False for individual files
                    individual_request = ReplayRequest(
                        source=request.source,
                        id_or_path=request.id_or_path,
                        mode=request.mode,
                        rate_lines_per_sec=request.rate_lines_per_sec,
                        loop=False,  # Individual files should NOT loop
                        jitter_ms=request.jitter_ms,
                        otlp_endpoint=request.otlp_endpoint
                    )
                    
                    # Replay this specific file (once)
                    logger.info(f"🎬 Replaying {file_key}: {len(content_lines)} lines (cycle {cycle_count})")
                    _replay_logs(source_path, individual_request, stop_event)
                    replayed_count += 1
                    
                except Exception as e:
                    logger.error(f"❌ Error processing file {file_key}: {e}")
                    skipped_count += 1
                    continue
                
                if stop_event.is_set() or global_stop_flag.is_set():
                    logger.info("🛑 Replay all stopped by user (after file)")
                    return
                    
                # Small delay between files  
                time.sleep(0.5)
                
            logger.info(f"Completed cycle {cycle_count}: {replayed_count} replayed, {skipped_count} skipped")
            
            # Check for stop before deciding to loop the entire sequence
            if stop_event.is_set() or global_stop_flag.is_set():
                logger.info("🛑 Replay all stopped by user (before sequence loop decision)")
                return
            
            # Check if we should loop the entire sequence
            if not request.loop:
                break
                
            logger.info(f"🔄 Looping back to start of all files (beginning cycle {cycle_count + 1})...")
            
        logger.info(f"Completed replay all after {cycle_count} cycles")
        
    except Exception as e:
        logger.error(f"Error during replay all: {e}")
    finally:
        # CRITICAL FIX: Always clean up state, even on exceptions
        replay_state["active"] = False
        replay_state["current_job"] = None
        replay_state["stop_event"] = None
        logger.info("Replay all completed and state cleaned up")

def _replay_all_uploaded(request: ReplayRequest, stop_event: threading.Event):
    """Replay all uploaded files sequentially"""
    try:
        # Get all uploaded files, sorted by modification time (newest first)
        uploaded_files = list(UPLOADS_DIR.glob("*.log"))
        uploaded_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        files_to_replay = [(f.name, str(f)) for f in uploaded_files]
        total_files = len(files_to_replay)
        cycle_count = 0
        
        logger.info(f"Starting replay of all {total_files} uploaded files with loop={request.loop}")
        
        # Handle looping at the "all files" level, not individual file level
        while True:
            if stop_event.is_set() or global_stop_flag.is_set():
                logger.info("🛑 Replay all uploaded stopped by user (outer loop)")
                return
                
            cycle_count += 1
            replayed_count = 0
            skipped_count = 0
            
            logger.info(f"🔄 Starting cycle {cycle_count} of all uploaded files")
            
            for file_index, (file_name, file_path) in enumerate(files_to_replay, 1):
                if stop_event.is_set() or global_stop_flag.is_set():
                    logger.info("🛑 Replay all uploaded stopped by user (file loop)")
                    return
                    
                logger.info(f"Processing uploaded file {file_index}/{total_files}: {file_name} (cycle {cycle_count})")
                
                # Update current job info to show progress
                if replay_state["current_job"]:
                    replay_state["current_job"]["current_file"] = file_name
                    replay_state["current_job"]["progress"] = f"{file_index}/{total_files}"
                    replay_state["current_job"]["cycle"] = cycle_count
                
                # Pre-validate file before attempting replay
                source_path = Path(file_path)
                
                try:
                    file_size = source_path.stat().st_size
                    if file_size == 0:
                        logger.warning(f"⚠️  Skipping empty uploaded file: {file_name} (0 bytes)")
                        skipped_count += 1
                        continue
                    
                    # Quick content check
                    with open(source_path, 'r') as f:
                        content_lines = [line.strip() for line in f if line.strip()]
                    
                    if len(content_lines) == 0:
                        logger.warning(f"⚠️  Skipping uploaded file with no content: {file_name} (no valid lines)")
                        skipped_count += 1
                        continue
                    
                    # Create a modified request with loop=False for individual files
                    individual_request = ReplayRequest(
                        source=request.source,
                        id_or_path=request.id_or_path,
                        mode=request.mode,
                        rate_lines_per_sec=request.rate_lines_per_sec,
                        loop=False,  # Individual files should NOT loop
                        jitter_ms=request.jitter_ms,
                        otlp_endpoint=request.otlp_endpoint
                    )
                    
                    # Replay this specific file (once)
                    logger.info(f"🎬 Replaying uploaded {file_name}: {len(content_lines)} lines (cycle {cycle_count})")
                    _replay_logs(source_path, individual_request, stop_event)
                    replayed_count += 1
                    
                except Exception as e:
                    logger.error(f"❌ Error processing uploaded file {file_name}: {e}")
                    skipped_count += 1
                    continue
                
                if stop_event.is_set() or global_stop_flag.is_set():
                    logger.info("🛑 Replay all uploaded stopped by user (after file)")
                    return
                    
                # Small delay between files  
                time.sleep(0.5)
                
            logger.info(f"Completed uploaded cycle {cycle_count}: {replayed_count} replayed, {skipped_count} skipped")
            
            # Check for stop before deciding to loop the entire sequence
            if stop_event.is_set() or global_stop_flag.is_set():
                logger.info("🛑 Replay all uploaded stopped by user (before sequence loop decision)")
                return
            
            # Check if we should loop the entire sequence
            if not request.loop:
                break
                
            logger.info(f"🔄 Looping back to start of all uploaded files (beginning cycle {cycle_count + 1})...")
            
        logger.info(f"Completed replay all uploaded after {cycle_count} cycles")
        
    except Exception as e:
        logger.error(f"Error during replay all uploaded: {e}")
    finally:
        # CRITICAL FIX: Always clean up state, even on exceptions
        replay_state["active"] = False
        replay_state["current_job"] = None
        replay_state["stop_event"] = None # Ensure stop_event is cleared
        logger.info("Replay all uploaded completed and state cleaned up")

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
    # Auto-load sample log files on startup
    auto_load_sample_logs()
    
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

