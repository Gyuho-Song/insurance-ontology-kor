export const PROJECT_PREFIX = 'ontology-demo';

export const STACK_NAMES = {
  VPC: `${PROJECT_PREFIX}-vpc`,
  DATA: `${PROJECT_PREFIX}-data`,
  EKS: `${PROJECT_PREFIX}-eks`,
  CLOUDFRONT: `${PROJECT_PREFIX}-cloudfront`,
} as const;

export const RESOURCE_NAMES = {
  // Neptune
  NEPTUNE_CLUSTER: `${PROJECT_PREFIX}-neptune`,
  NEPTUNE_SUBNET_GROUP: `${PROJECT_PREFIX}-neptune-subnet`,

  // OpenSearch
  OPENSEARCH_COLLECTION: 'ontology-embeddings',
  OPENSEARCH_INDEX: 'ontology-vectors',

  // S3
  PARSED_BUCKET: `${PROJECT_PREFIX}-parsed-data`,
  MOCK_CACHE_BUCKET: `${PROJECT_PREFIX}-mock-cache`,

  // EKS
  EKS_CLUSTER: `${PROJECT_PREFIX}-cluster`,
  EKS_NAMESPACE: 'ontology-demo',
  FASTAPI_SA: 'fastapi-sa',
  NEXTJS_SA: 'nextjs-sa',

  // ECR
  BACKEND_REPO: `${PROJECT_PREFIX}/backend-app`,
  FRONTEND_REPO: `${PROJECT_PREFIX}/frontend-app`,
} as const;

export const DEFAULT_TAGS: Record<string, string> = {
  Project: 'OntologyGraphRAGDemo',
  ManagedBy: 'CDK',
};

export const VECTOR_DIMENSION = 1536; // Bedrock Titan Embedding

// ACM Certificate for ALB HTTPS (legacy, kept for reference)
export const ACM_CERTIFICATE_ARN =
  'arn:aws:acm:us-west-2:123456789012:certificate/00000000-0000-0000-0000-000000000000';

// Security: EKS admin access
export const ADMIN_EC2_CIDR = '203.0.113.0/32';

// Security: CloudFront → ALB origin verification header
export const CF_ORIGIN_VERIFY_HEADER = 'X-Origin-Verify';
export const CF_ORIGIN_VERIFY_SECRET = 'CHANGE_ME_CF_ORIGIN_VERIFY_SECRET';
