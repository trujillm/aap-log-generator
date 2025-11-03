# Environment-Specific Helm Values

This directory contains environment-specific values files for deploying the AAP Mock Service using Helm.

## Available Environments

| Environment | File | Description |
|-------------|------|-------------|
| **Development** | `values-dev.yaml` | Lightweight config for development/testing |
| **Production** | `values-prod.yaml` | Production-ready with HA and security |

## Usage

### Development Deployment
```bash
helm upgrade --install aap-mock-dev ./chart/aap-mock \
  --namespace development --create-namespace \
  --values environments/values-dev.yaml
```

### Production Deployment  
```bash
helm upgrade --install aap-mock-prod ./chart/aap-mock \
  --namespace production --create-namespace \
  --values environments/values-prod.yaml
```

## Creating Custom Environments

1. Copy an existing values file:
```bash
cp environments/values-dev.yaml environments/values-staging.yaml
```

2. Modify for your environment:
- Update `image.tag` for specific versions
- Adjust `resources` and `persistence` sizes
- Configure environment-specific `app.env` variables
- Set appropriate `route.tls` settings

3. Deploy with your custom values:
```bash
helm upgrade --install aap-mock-staging ./chart/aap-mock \
  --namespace staging --create-namespace \
  --values environments/values-staging.yaml
```

## Best Practices

- **Use specific image tags** in production (not `latest`)
- **Set resource limits** appropriate for your cluster
- **Configure TLS termination** for production routes  
- **Set environment variables** for observability integration
- **Use separate namespaces** for environment isolation

## Security Notes

- Never commit files containing secrets to version control
- Use Kubernetes Secrets or external secret management for sensitive data
- Consider using `helm secrets` plugin for encrypted values files
