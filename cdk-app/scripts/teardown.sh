#!/bin/bash
set -euo pipefail

echo "============================================"
echo "  Ontology GraphRAG Demo — Resource Cleanup"
echo "============================================"
echo ""
echo "This will destroy ALL CDK stacks."
echo "Use to save costs when demo is not in use."
echo ""

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"

cd "$(dirname "$0")/.."

read -p "Are you sure? (y/N): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

echo ""
echo ">>> Destroying all stacks..."
npx cdk destroy --all --force --region "$REGION"

echo ""
echo "============================================"
echo "  All resources destroyed."
echo "  Run ./deploy.sh to redeploy."
echo "============================================"
