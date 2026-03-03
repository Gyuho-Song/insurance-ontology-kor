import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as neptune from 'aws-cdk-lib/aws-neptune';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { EksStack } from '../../lib/stacks/eks-stack';

describe('EksStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const mockStack = new cdk.Stack(app, 'MockStack', {
      env: { account: '123456789012', region: 'ap-northeast-2' },
    });

    const vpc = new ec2.Vpc(mockStack, 'MockVpc', {
      maxAzs: 2,
      subnetConfiguration: [
        { name: 'Public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'AppPrivate', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: 'DataPrivate', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });
    const eksSg = new ec2.SecurityGroup(mockStack, 'EksSg', { vpc });
    const neptuneCluster = new neptune.CfnDBCluster(mockStack, 'NeptuneCluster', {
      iamAuthEnabled: true,
    });
    const parsedBucket = new s3.Bucket(mockStack, 'ParsedBucket');
    const mockCacheBucket = new s3.Bucket(mockStack, 'MockCacheBucket');

    const stack = new EksStack(app, 'TestEksStack', {
      env: { account: '123456789012', region: 'ap-northeast-2' },
      vpc,
      eksSecurityGroup: eksSg,
      neptuneCluster,
      neptuneClusterEndpoint: 'test-neptune.cluster-xxx.ap-northeast-2.neptune.amazonaws.com',
      neptuneClusterPort: '8182',
      opensearchCollectionArn: 'arn:aws:aoss:ap-northeast-2:123456789012:collection/test',
      opensearchCollectionEndpoint: 'https://test.aoss.ap-northeast-2.amazonaws.com',
      parsedBucket,
      mockCacheBucket,
      instanceType: 'm5.xlarge',
      minSize: 2,
      maxSize: 4,
      desiredSize: 2,
    });
    template = Template.fromStack(stack);
  });

  test('creates EKS cluster', () => {
    template.hasResourceProperties('Custom::AWSCDK-EKS-Cluster', {
      Config: Match.objectLike({
        name: 'ontology-demo-cluster',
        version: '1.33',
      }),
    });
  });

  test('creates managed node group with m5.xlarge', () => {
    template.hasResourceProperties('AWS::EKS::Nodegroup', {
      InstanceTypes: ['m5.xlarge'],
      ScalingConfig: {
        MinSize: 2,
        MaxSize: 4,
        DesiredSize: 2,
      },
    });
  });

  test('creates ECR repositories', () => {
    template.hasResourceProperties('AWS::ECR::Repository', {
      RepositoryName: 'ontology-demo/backend-app',
    });
    template.hasResourceProperties('AWS::ECR::Repository', {
      RepositoryName: 'ontology-demo/frontend-app',
    });
  });

  test('creates IRSA roles for FastAPI and NextJS', () => {
    const roles = template.findResources('AWS::IAM::Role');
    const irsaRoles = Object.values(roles).filter((role: any) =>
      JSON.stringify(role.Properties?.AssumeRolePolicyDocument).includes('sts:AssumeRoleWithWebIdentity'),
    );
    expect(irsaRoles.length).toBeGreaterThanOrEqual(2);
  });

  test('exports cluster name', () => {
    template.hasOutput('EksClusterName', {
      Export: { Name: 'EksClusterName' },
    });
  });
});
