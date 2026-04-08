#!/bin/bash

API_URL="${1:-http://localhost:8000}"

echo "[$(date)] Health check: $API_URL"

curl -s "$API_URL/health" | grep -q "ok" && echo "✓ API OK" || echo "✗ API ERRO"
