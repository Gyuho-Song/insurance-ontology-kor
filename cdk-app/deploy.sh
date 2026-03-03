#!/bin/bash
set -euo pipefail

echo "============================================"
echo "  Ontology GraphRAG Demo — Full Deployment"
echo "============================================"

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
CLUSTER_NAME="ontology-demo-cluster"

cd "$(dirname "$0")"

# 1. Install dependencies
echo ""
echo ">>> Step 1/5: Installing dependencies..."
npm ci

# 2. CDK Bootstrap (if not already done)
echo ""
echo ">>> Step 2/5: CDK Bootstrap..."
npx cdk bootstrap --region "$REGION" 2>/dev/null || echo "Bootstrap already done"

# 3. CDK Deploy
echo ""
echo ">>> Step 3/5: CDK Deploy (all stacks)..."
npx cdk deploy --all --require-approval never --region "$REGION"

# 4. Configure kubectl
echo ""
echo ">>> Step 4/5: Configuring kubectl..."
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION"

# 5. Verify deployment
echo ""
echo ">>> Step 5/5: Verifying deployment..."
echo ""
echo "--- EKS Nodes ---"
kubectl get nodes
echo ""
echo "--- Namespace ---"
kubectl get ns ontology-demo
echo ""
echo "--- Pods ---"
kubectl get pods -n ontology-demo
echo ""
echo "--- Services ---"
kubectl get svc -n ontology-demo
echo ""
echo "--- Ingress ---"
kubectl get ingress -n ontology-demo

echo ""
echo "============================================"
echo "  Stack Outputs"
echo "============================================"
aws cloudformation describe-stacks \
  --query 'Stacks[?contains(StackName, `ontology-demo`)].Outputs[]' \
  --output table \
  --region "$REGION"

echo ""
echo "============================================"
echo "  Deployment Complete!"
echo "============================================"
