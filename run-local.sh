#!/bin/bash

# Local development runner for AAP Log Generator
set -euo pipefail

echo "🏗️  Building container image..."
podman build -t aap-mock:local .

echo "📁 Setting permissions on data directories..."
chmod -R 777 ./data ./logs

echo "🚀 Starting AAP Mock service..."
echo "   - API will be available at: http://localhost:8080"
echo "   - Health check: http://localhost:8080/healthz" 
echo "   - API docs: http://localhost:8080/docs"
echo "   - Data persisted in: ./data/"
echo "   - Logs written to: ./logs/output.log"
echo "   - Auto-loading files from: ./sample-logs/"
echo ""
echo "💡 Drop .log or .txt files in ./sample-logs/ for auto-loading!"
echo "Press Ctrl+C to stop the service"

podman run --rm -p 8080:8080 --user $(id -u):$(id -g) \
  -v $(pwd)/data:/data \
  -v $(pwd)/logs:/var/log/aap-mock \
  -v $(pwd)/sample-logs:/app/sample-logs \
  aap-mock:local

