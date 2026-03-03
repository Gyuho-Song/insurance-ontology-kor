import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { VpcStack } from '../../lib/stacks/vpc-stack';

describe('VpcStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new VpcStack(app, 'TestVpcStack', {
      maxAzs: 2,
      natGateways: 1,
    });
    template = Template.fromStack(stack);
  });

  test('creates a VPC with correct CIDR', () => {
    template.hasResourceProperties('AWS::EC2::VPC', {
      CidrBlock: '10.0.0.0/16',
    });
  });

  test('creates 3 types of subnets (6 total for 2 AZs)', () => {
    template.resourceCountIs('AWS::EC2::Subnet', 6);
  });

  test('creates 1 NAT Gateway', () => {
    template.resourceCountIs('AWS::EC2::NatGateway', 1);
  });

  test('creates at least 3 security groups (EKS, Neptune, OpenSearch + VPC endpoint SGs)', () => {
    const sgs = template.findResources('AWS::EC2::SecurityGroup');
    expect(Object.keys(sgs).length).toBeGreaterThanOrEqual(3);
  });

  test('Neptune SG allows inbound 8182 from EKS SG', () => {
    template.hasResourceProperties('AWS::EC2::SecurityGroupIngress', {
      IpProtocol: 'tcp',
      FromPort: 8182,
      ToPort: 8182,
    });
  });

  test('creates S3 Gateway endpoint', () => {
    template.hasResourceProperties('AWS::EC2::VPCEndpoint', {
      VpcEndpointType: 'Gateway',
    });
  });

  test('creates interface VPC endpoints', () => {
    const endpoints = template.findResources('AWS::EC2::VPCEndpoint', {
      Properties: {
        VpcEndpointType: 'Interface',
      },
    });
    expect(Object.keys(endpoints).length).toBeGreaterThanOrEqual(4);
  });
});
