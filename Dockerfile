FROM registry.access.redhat.com/ubi8/python-39:latest

# Set working directory
WORKDIR /app

# Switch to root for system setup
USER 0

# Install curl for health checks
RUN yum update -y && yum install -y curl && yum clean all
RUN mkdir -p /data/uploads /data/generated /var/log/aap-mock && \
    chown -R 1001:0 /data /var/log/aap-mock && \
    chmod -R g=u /data /var/log/aap-mock

# Switch back to non-root user
USER 1001

# Copy requirements and install dependencies
COPY --chown=1001:0 requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=1001:0 main.py .

# Copy sample logs directory
COPY --chown=1001:0 sample-logs/ ./sample-logs/

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Set environment variables
ENV PORT=8080
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD ["python", "main.py"]

