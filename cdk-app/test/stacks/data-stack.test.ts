import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Template } from 'aws-cdk-lib/assertions';
import { DataStack } from '../../lib/stacks/data-stack';

describe('DataStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();

    // Create a mock VPC
    const vpcStack = new cdk.Stack(app, 'MockVpcStack');
    const vpc = new ec2.Vpc(vpcStack, 'MockVpc', {
      maxAzs: 2,
      subnetConfiguration: [
        { name: 'Public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'AppPrivate', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: 'DataPrivate', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });
    const neptuneSg = new ec2.SecurityGroup(vpcStack, 'NeptuneSg', { vpc });
    const opensearchSg = new ec2.SecurityGroup(vpcStack, 'OpenSearchSg', { vpc });

    const stack = new DataStack(app, 'TestDataStack', {
      vpc,
      neptuneSecurityGroup: neptuneSg,
      opensearchSecurityGroup: opensearchSg,
      neptuneMinCapacity: 2.5,
      neptuneMaxCapacity: 128,
    });
    template = Template.fromStack(stack);
  });

  test('creates Neptune Serverless cluster', () => {
    template.hasResourceProperties('AWS::Neptune::DBCluster', {
      ServerlessScalingConfiguration: {
        MinCapacity: 2.5,
        MaxCapacity: 128,
      },
      IamAuthEnabled: true,
      StorageEncrypted: true,
    });
  });

  test('creates Neptune subnet group', () => {
    template.hasResource('AWS::Neptune::DBSubnetGroup', {});
  });

  test('creates OpenSearch Serverless collection', () => {
    template.hasResourceProperties('AWS::OpenSearchServerless::Collection', {
      Type: 'VECTORSEARCH',
    });
  });

  test('creates 2 S3 buckets (parsed + mock-cache)', () => {
    template.resourceCountIs('AWS::S3::Bucket', 2);
  });

  test('S3 buckets have encryption enabled', () => {
    template.hasResourceProperties('AWS::S3::Bucket', {
      BucketEncryption: {
        ServerSideEncryptionConfiguration: [
          {
            ServerSideEncryptionByDefault: {
              SSEAlgorithm: 'AES256',
            },
          },
        ],
      },
    });
  });

  test('S3 buckets block public access', () => {
    template.hasResourceProperties('AWS::S3::Bucket', {
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
    });
  });
});
