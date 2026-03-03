#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { VpcStack } from '../lib/stacks/vpc-stack';
import { DataStack } from '../lib/stacks/data-stack';
import { EksStack } from '../lib/stacks/eks-stack';
import { STACK_NAMES, DEFAULT_TAGS } from '../lib/config/constants';
import { DEMO_ENV } from '../lib/config/environments';

const app = new cdk.App();

// Apply global tags
for (const [key, value] of Object.entries({ ...DEFAULT_TAGS, ...DEMO_ENV.tags })) {
  cdk.Tags.of(app).add(key, value);
}

// =========================================
// Stack 1: VPC (Foundation)
// =========================================
const vpcStack = new VpcStack(app, STACK_NAMES.VPC, {
  env: DEMO_ENV.env,
  maxAzs: DEMO_ENV.vpc.maxAzs,
  natGateways: DEMO_ENV.vpc.natGateways,
});

// =========================================
// Stack 2: Data (Neptune + OpenSearch + S3)
// Depends on: VPC
// =========================================
const dataStack = new DataStack(app, STACK_NAMES.DATA, {
  env: DEMO_ENV.env,
  vpc: vpcStack.vpc,
  neptuneSecurityGroup: vpcStack.neptuneSecurityGroup,
  opensearchSecurityGroup: vpcStack.opensearchSecurityGroup,
  neptuneMinCapacity: DEMO_ENV.neptune.minCapacity,
  neptuneMaxCapacity: DEMO_ENV.neptune.maxCapacity,
});
dataStack.addDependency(vpcStack);

// =========================================
// Stack 3: EKS (Cluster + IRSA + K8s Manifests)
// Depends on: VPC, Data
// =========================================
const eksStack = new EksStack(app, STACK_NAMES.EKS, {
  env: DEMO_ENV.env,
  vpc: vpcStack.vpc,
  eksSecurityGroup: vpcStack.eksSecurityGroup,
  neptuneSecurityGroup: vpcStack.neptuneSecurityGroup,
  opensearchSecurityGroup: vpcStack.opensearchSecurityGroup,

  // Data Stack
  neptuneClusterEndpoint: dataStack.neptuneClusterEndpoint,
  neptuneClusterPort: dataStack.neptuneClusterPort,
  opensearchCollectionArn: dataStack.opensearchCollectionArn,
  opensearchCollectionEndpoint: dataStack.opensearchCollectionEndpoint,
  parsedBucket: dataStack.parsedBucket,
  mockCacheBucket: dataStack.mockCacheBucket,

  // EKS config
  instanceType: DEMO_ENV.eks.instanceType,
  minSize: DEMO_ENV.eks.minSize,
  maxSize: DEMO_ENV.eks.maxSize,
  desiredSize: DEMO_ENV.eks.desiredSize,
});
eksStack.addDependency(vpcStack);
eksStack.addDependency(dataStack);

app.synth();
