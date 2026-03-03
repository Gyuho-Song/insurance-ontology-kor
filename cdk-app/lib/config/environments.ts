import { Environment } from 'aws-cdk-lib';

export interface EnvironmentConfig {
  readonly env: Environment;
  readonly vpc: {
    readonly maxAzs: number;
    readonly natGateways: number;
  };
  readonly eks: {
    readonly instanceType: string;
    readonly minSize: number;
    readonly maxSize: number;
    readonly desiredSize: number;
  };
  readonly neptune: {
    readonly minCapacity: number;
    readonly maxCapacity: number;
  };
  readonly tags: Record<string, string>;
}

export const DEMO_ENV: EnvironmentConfig = {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-2',
  },

  vpc: {
    maxAzs: 2,
    natGateways: 1,
  },

  eks: {
    instanceType: 'm5.xlarge',
    minSize: 2,
    maxSize: 4,
    desiredSize: 2,
  },

  neptune: {
    minCapacity: 2.5,
    maxCapacity: 128,
  },

  tags: {
    Project: 'OntologyGraphRAGDemo',
    Environment: 'demo',
    ManagedBy: 'CDK',
  },
};
