#!/bin/bash
set -euo pipefail

echo "============================================"
echo "  Neptune Warm-up (Manual Trigger)"
echo "============================================"
echo ""
echo "Use this script before a demo to ensure"
echo "Neptune NCUs are warm and caches are loaded."
echo ""

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
FUNCTION_NAME="ontology-demo-neptune-warmup"

echo ">>> Invoking Neptune warm-up Lambda..."
aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --payload '{}' \
  --cli-read-timeout 120 \
  /tmp/warmup-response.json

echo ""
echo ">>> Response:"
cat /tmp/warmup-response.json
echo ""
echo ""
echo ">>> Warm-up complete!"
echo ">>> Neptune NCUs should now be active."
