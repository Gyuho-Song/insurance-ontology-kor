import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as neptune from 'aws-cdk-lib/aws-neptune';
import * as opensearch from 'aws-cdk-lib/aws-opensearchserverless';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import { RESOURCE_NAMES } from '../config/constants';

export interface DataStackProps extends cdk.StackProps {
  readonly vpc: ec2.IVpc;
  readonly neptuneSecurityGroup: ec2.ISecurityGroup;
  readonly opensearchSecurityGroup: ec2.ISecurityGroup;
  readonly neptuneMinCapacity: number;
  readonly neptuneMaxCapacity: number;
}

export class DataStack extends cdk.Stack {
  public readonly neptuneCluster: neptune.CfnDBCluster;
  public readonly neptuneClusterEndpoint: string;
  public readonly neptuneClusterPort: string;
  public readonly opensearchCollectionArn: string;
  public readonly opensearchCollectionEndpoint: string;
  public readonly parsedBucket: s3.IBucket;
  public readonly mockCacheBucket: s3.IBucket;

  constructor(scope: Construct, id: string, props: DataStackProps) {
    super(scope, id, props);

    const dataSubnets = props.vpc.selectSubnets({
      subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
    });

    // =========================================
    // Neptune Serverless
    // =========================================

    const neptuneSubnetGroup = new neptune.CfnDBSubnetGroup(this, 'NeptuneSubnetGroup', {
      dbSubnetGroupDescription: 'Neptune Serverless subnet group',
      dbSubnetGroupName: RESOURCE_NAMES.NEPTUNE_SUBNET_GROUP,
      subnetIds: dataSubnets.subnetIds,
    });

    this.neptuneCluster = new neptune.CfnDBCluster(this, 'NeptuneCluster', {
      dbClusterIdentifier: RESOURCE_NAMES.NEPTUNE_CLUSTER,
      engineVersion: '1.3.2.1',
      dbSubnetGroupName: neptuneSubnetGroup.dbSubnetGroupName,
      vpcSecurityGroupIds: [props.neptuneSecurityGroup.securityGroupId],
      iamAuthEnabled: true,
      storageEncrypted: true,
      serverlessScalingConfiguration: {
        minCapacity: props.neptuneMinCapacity,
        maxCapacity: props.neptuneMaxCapacity,
      },
      backupRetentionPeriod: 7,
      deletionProtection: false, // Demo environment
    });
    this.neptuneCluster.addDependency(neptuneSubnetGroup);

    // Neptune Serverless Instance (required for cluster endpoint to be active)
    const neptuneInstance = new neptune.CfnDBInstance(this, 'NeptuneInstance', {
      dbInstanceIdentifier: `${RESOURCE_NAMES.NEPTUNE_CLUSTER}-instance`,
      dbInstanceClass: 'db.serverless',
      dbClusterIdentifier: this.neptuneCluster.dbClusterIdentifier!,
    });
    neptuneInstance.addDependency(this.neptuneCluster);

    this.neptuneClusterEndpoint = this.neptuneCluster.attrEndpoint;
    this.neptuneClusterPort = this.neptuneCluster.attrPort;

    // =========================================
    // OpenSearch Serverless (Vector Search)
    // =========================================

    // Encryption Policy
    const encryptionPolicy = new opensearch.CfnSecurityPolicy(this, 'OSSEncryptionPolicy', {
      name: `${RESOURCE_NAMES.OPENSEARCH_COLLECTION}-enc`,
      type: 'encryption',
      policy: JSON.stringify({
        Rules: [
          {
            Resource: [`collection/${RESOURCE_NAMES.OPENSEARCH_COLLECTION}`],
            ResourceType: 'collection',
          },
        ],
        AWSOwnedKey: true,
      }),
    });

    // OpenSearch Serverless VPC Endpoint (must be created before Network Policy)
    const ossVpcEndpoint = new opensearch.CfnVpcEndpoint(this, 'OSSVpcEndpoint', {
      name: `${RESOURCE_NAMES.OPENSEARCH_COLLECTION}-vpce`,
      vpcId: props.vpc.vpcId,
      subnetIds: dataSubnets.subnetIds,
      securityGroupIds: [props.opensearchSecurityGroup.securityGroupId],
    });

    // Network Policy — references VPC Endpoint ID
    const networkPolicy = new opensearch.CfnSecurityPolicy(this, 'OSSNetworkPolicy', {
      name: `${RESOURCE_NAMES.OPENSEARCH_COLLECTION}-net`,
      type: 'network',
      policy: cdk.Fn.sub(
        JSON.stringify([
          {
            Rules: [
              {
                Resource: [`collection/${RESOURCE_NAMES.OPENSEARCH_COLLECTION}`],
                ResourceType: 'collection',
              },
            ],
            AllowFromPublic: false,
            SourceVPCEs: ['${VpceId}'],
          },
        ]),
        { VpceId: ossVpcEndpoint.attrId },
      ),
    });
    networkPolicy.addDependency(ossVpcEndpoint);

    // Collection
    const collection = new opensearch.CfnCollection(this, 'OSSCollection', {
      name: RESOURCE_NAMES.OPENSEARCH_COLLECTION,
      type: 'VECTORSEARCH',
      description: 'Insurance ontology vector embeddings',
    });
    collection.addDependency(encryptionPolicy);
    collection.addDependency(networkPolicy);

    this.opensearchCollectionArn = collection.attrArn;
    this.opensearchCollectionEndpoint = collection.attrCollectionEndpoint;

    // Data Access Policy — grants full data access to all IAM principals in this account
    new opensearch.CfnAccessPolicy(this, 'OSSDataAccessPolicy', {
      name: `${RESOURCE_NAMES.OPENSEARCH_COLLECTION}-access`,
      type: 'data',
      policy: JSON.stringify([
        {
          Description: 'Full data access for index and collection operations',
          Rules: [
            {
              Resource: [`index/${RESOURCE_NAMES.OPENSEARCH_COLLECTION}/*`],
              Permission: ['aoss:*'],
              ResourceType: 'index',
            },
            {
              Resource: [`collection/${RESOURCE_NAMES.OPENSEARCH_COLLECTION}`],
              Permission: ['aoss:*'],
              ResourceType: 'collection',
            },
          ],
          Principal: [`arn:aws:iam::${this.account}:root`],
        },
      ]),
    });

    // =========================================
    // S3 Buckets
    // =========================================

    const commonBucketProps: Partial<s3.BucketProps> = {
      encryption: s3.BucketEncryption.S3_MANAGED,
      versioned: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Demo environment
      autoDeleteObjects: true,
    };

    this.parsedBucket = new s3.Bucket(this, 'ParsedDataBucket', {
      ...commonBucketProps,
      bucketName: `${RESOURCE_NAMES.PARSED_BUCKET}-${this.account}-${this.region}`,
    });

    this.mockCacheBucket = new s3.Bucket(this, 'MockCacheBucket', {
      ...commonBucketProps,
      bucketName: `${RESOURCE_NAMES.MOCK_CACHE_BUCKET}-${this.account}-${this.region}`,
      cors: [
        {
          allowedHeaders: ['*'],
          allowedMethods: [s3.HttpMethods.GET],
          allowedOrigins: ['*'], // Tightened in production
          maxAge: 3600,
        },
      ],
    });

    // =========================================
    // Outputs
    // =========================================

    new cdk.CfnOutput(this, 'NeptuneClusterEndpoint', {
      value: this.neptuneClusterEndpoint,
      exportName: 'NeptuneClusterEndpoint',
    });
    new cdk.CfnOutput(this, 'NeptuneClusterPort', {
      value: this.neptuneClusterPort,
      exportName: 'NeptuneClusterPort',
    });
    new cdk.CfnOutput(this, 'OpenSearchCollectionEndpoint', {
      value: this.opensearchCollectionEndpoint,
      exportName: 'OpenSearchCollectionEndpoint',
    });
    new cdk.CfnOutput(this, 'ParsedBucketName', {
      value: this.parsedBucket.bucketName,
      exportName: 'ParsedDataBucketName',
    });
    new cdk.CfnOutput(this, 'MockCacheBucketName', {
      value: this.mockCacheBucket.bucketName,
      exportName: 'MockCacheBucketName',
    });
  }
}
