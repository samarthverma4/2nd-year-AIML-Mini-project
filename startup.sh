#!/bin/bash
# Azure App Service (Linux Python) startup command.
# Configure in Azure Portal → App Service → Configuration → General settings → Startup Command:
#   bash startup.sh

# Generate a fresh JWT secret on every container start so all gunicorn workers
# share the same value but every restart invalidates existing tokens.
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

gunicorn --bind=0.0.0.0 --chdir server --timeout 600 --workers 2 main:app
