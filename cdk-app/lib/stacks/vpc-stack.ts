import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';
import { RESOURCE_NAMES } from '../config/constants';

export interface VpcStackProps extends cdk.StackProps {
  readonly maxAzs: number;
  readonly natGateways: number;
}

export class VpcStack extends cdk.Stack {
  public readonly vpc: ec2.IVpc;
  public readonly eksSecurityGroup: ec2.ISecurityGroup;
  public readonly neptuneSecurityGroup: ec2.ISecurityGroup;
  public readonly opensearchSecurityGroup: ec2.ISecurityGroup;

  constructor(scope: Construct, id: string, props: VpcStackProps) {
    super(scope, id, props);

    // --- VPC with 3-tier subnets ---
    this.vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: props.maxAzs,
      natGateways: props.natGateways,
      ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/16'),
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'AppPrivate',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
        {
          name: 'DataPrivate',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    // --- Security Groups ---

    // EKS Worker Nodes SG
    this.eksSecurityGroup = new ec2.SecurityGroup(this, 'EksWorkersSg', {
      vpc: this.vpc,
      description: 'EKS Worker Nodes Security Group',
      allowAllOutbound: true,
    });

    // Neptune SG — only accept 8182 from EKS Workers
    this.neptuneSecurityGroup = new ec2.SecurityGroup(this, 'NeptuneSg', {
      vpc: this.vpc,
      description: 'Neptune Serverless Security Group',
      allowAllOutbound: false,
    });
    this.neptuneSecurityGroup.addIngressRule(
      this.eksSecurityGroup,
      ec2.Port.tcp(8182),
      'Allow Gremlin from EKS Workers',
    );

    // OpenSearch SG — only accept 443 from EKS Workers
    this.opensearchSecurityGroup = new ec2.SecurityGroup(this, 'OpenSearchSg', {
      vpc: this.vpc,
      description: 'OpenSearch Serverless Security Group',
      allowAllOutbound: false,
    });
    this.opensearchSecurityGroup.addIngressRule(
      this.eksSecurityGroup,
      ec2.Port.tcp(443),
      'Allow HTTPS from EKS Workers',
    );

    // --- VPC Endpoints ---

    // S3 Gateway Endpoint (free)
    this.vpc.addGatewayEndpoint('S3Endpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3,
    });

    // Interface Endpoints
    const interfaceEndpoints: Array<{ id: string; service: ec2.InterfaceVpcEndpointAwsService }> = [
      { id: 'StsEndpoint', service: ec2.InterfaceVpcEndpointAwsService.STS },
      { id: 'EcrEndpoint', service: ec2.InterfaceVpcEndpointAwsService.ECR },
      { id: 'EcrDockerEndpoint', service: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER },
      { id: 'CloudWatchLogsEndpoint', service: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS },
      // Karpenter requires SSM (AMI discovery), EC2 (instance mgmt), SQS (interruption)
      { id: 'SsmEndpoint', service: ec2.InterfaceVpcEndpointAwsService.SSM },
      { id: 'Ec2Endpoint', service: ec2.InterfaceVpcEndpointAwsService.EC2 },
      { id: 'SqsEndpoint', service: ec2.InterfaceVpcEndpointAwsService.SQS },
    ];

    for (const ep of interfaceEndpoints) {
      this.vpc.addInterfaceEndpoint(ep.id, {
        service: ep.service,
        subnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      });
    }

    // --- Karpenter Discovery Tags ---
    for (const subnet of this.vpc.selectSubnets({ subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS }).subnets) {
      cdk.Tags.of(subnet).add('karpenter.sh/discovery', RESOURCE_NAMES.EKS_CLUSTER);
    }
    cdk.Tags.of(this.eksSecurityGroup).add('karpenter.sh/discovery', RESOURCE_NAMES.EKS_CLUSTER);

    // --- Outputs ---
    new cdk.CfnOutput(this, 'VpcId', { value: this.vpc.vpcId });
  }
}
