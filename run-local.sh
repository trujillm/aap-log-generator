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
echo ""
echo "Press Ctrl+C to stop the service"

podman run --rm -p 8080:8080 \
  -v $(pwd)/data:/data \
  -v $(pwd)/logs:/var/log/aap-mock \
  aap-mock:local

