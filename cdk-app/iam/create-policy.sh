#!/bin/bash
set -euo pipefail

POLICY_NAME="OntologyDemoCdkDeployPolicy"
POLICY_FILE="$(dirname "$0")/cdk-deploy-policy.json"

echo "Creating IAM Policy: $POLICY_NAME"

# Check if policy already exists
EXISTING=$(aws iam list-policies --query "Policies[?PolicyName=='${POLICY_NAME}'].Arn" --output text 2>/dev/null || true)

if [ -n "$EXISTING" ] && [ "$EXISTING" != "None" ]; then
  echo "Policy already exists: $EXISTING"
  echo "Updating with new version..."

  # Delete oldest non-default version if at max (5 versions)
  VERSIONS=$(aws iam list-policy-versions --policy-arn "$EXISTING" --query "Versions[?!IsDefaultVersion].VersionId" --output text)
  for v in $VERSIONS; do
    aws iam delete-policy-version --policy-arn "$EXISTING" --version-id "$v" 2>/dev/null || true
  done

  aws iam create-policy-version \
    --policy-arn "$EXISTING" \
    --policy-document "file://${POLICY_FILE}" \
    --set-as-default

  echo "Policy updated: $EXISTING"
else
  RESULT=$(aws iam create-policy \
    --policy-name "$POLICY_NAME" \
    --policy-document "file://${POLICY_FILE}" \
    --description "CDK deployment policy for Ontology GraphRAG Demo" \
    --query "Policy.Arn" \
    --output text)

  echo "Policy created: $RESULT"
fi

echo ""
echo "=== Next Steps ==="
echo "Attach this policy to your deployment IAM user or role:"
echo ""
echo "  # For IAM User:"
echo "  aws iam attach-user-policy --user-name <YOUR_USER> --policy-arn <POLICY_ARN>"
echo ""
echo "  # For IAM Role (e.g., EC2 instance role):"
echo "  aws iam attach-role-policy --role-name <YOUR_ROLE> --policy-arn <POLICY_ARN>"
