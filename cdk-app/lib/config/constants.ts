export const PROJECT_PREFIX = 'od-euw1';

export const STACK_NAMES = {
  VPC: `${PROJECT_PREFIX}-vpc`,
  DATA: `${PROJECT_PREFIX}-data`,
  EKS: `${PROJECT_PREFIX}-eks`,
} as const;

export const RESOURCE_NAMES = {
  // Neptune
  NEPTUNE_CLUSTER: `${PROJECT_PREFIX}-neptune`,
  NEPTUNE_SUBNET_GROUP: `${PROJECT_PREFIX}-neptune-subnet`,

  // OpenSearch
  OPENSEARCH_COLLECTION: `${PROJECT_PREFIX}-embed`,
  OPENSEARCH_INDEX: 'ontology-vectors',

  // S3
  PARSED_BUCKET: `${PROJECT_PREFIX}-data`,
  MOCK_CACHE_BUCKET: `${PROJECT_PREFIX}-cache`,

  // EKS
  EKS_CLUSTER: `${PROJECT_PREFIX}-cluster`,
  EKS_NAMESPACE: `${PROJECT_PREFIX}`,
  FASTAPI_SA: 'fastapi-sa',
  NEXTJS_SA: 'nextjs-sa',

  // ECR
  BACKEND_REPO: `${PROJECT_PREFIX}/backend`,
  FRONTEND_REPO: `${PROJECT_PREFIX}/frontend`,
} as const;

export const DEFAULT_TAGS: Record<string, string> = {
  Project: 'OntologyGraphRAGDemo',
  ManagedBy: 'CDK',
};

export const VECTOR_DIMENSION = 1024; // Bedrock Titan Embed V2
