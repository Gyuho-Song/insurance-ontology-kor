import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as eks from 'aws-cdk-lib/aws-eks';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { KubectlV33Layer } from '@aws-cdk/lambda-layer-kubectl-v33';
import { Construct } from 'constructs';
import { RESOURCE_NAMES } from '../config/constants';

export interface EksStackProps extends cdk.StackProps {
  readonly vpc: ec2.IVpc;
  readonly eksSecurityGroup: ec2.ISecurityGroup;
  readonly neptuneSecurityGroup: ec2.ISecurityGroup;
  readonly opensearchSecurityGroup: ec2.ISecurityGroup;

  // Data Stack resources
  readonly neptuneClusterEndpoint: string;
  readonly neptuneClusterPort: string;
  readonly opensearchCollectionArn: string;
  readonly opensearchCollectionEndpoint: string;
  readonly parsedBucket: s3.IBucket;
  readonly mockCacheBucket: s3.IBucket;

  // EKS node config
  readonly instanceType: string;
  readonly minSize: number;
  readonly maxSize: number;
  readonly desiredSize: number;
}

export class EksStack extends cdk.Stack {
  public readonly cluster: eks.Cluster;
  public readonly fastapiServiceAccount: eks.ServiceAccount;
  public readonly nextjsServiceAccount: eks.ServiceAccount;
  public readonly backendRepo: ecr.Repository;
  public readonly frontendRepo: ecr.Repository;

  constructor(scope: Construct, id: string, props: EksStackProps) {
    super(scope, id, props);

    // =========================================
    // ECR Repositories
    // =========================================

    this.backendRepo = new ecr.Repository(this, 'BackendRepo', {
      repositoryName: RESOURCE_NAMES.BACKEND_REPO,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [{ maxImageCount: 10 }],
    });

    this.frontendRepo = new ecr.Repository(this, 'FrontendRepo', {
      repositoryName: RESOURCE_NAMES.FRONTEND_REPO,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [{ maxImageCount: 10 }],
    });

    // =========================================
    // EKS Cluster
    // =========================================

    this.cluster = new eks.Cluster(this, 'EksCluster', {
      clusterName: RESOURCE_NAMES.EKS_CLUSTER,
      version: eks.KubernetesVersion.V1_33,
      kubectlLayer: new KubectlV33Layer(this, 'KubectlLayer'),
      vpc: props.vpc,
      vpcSubnets: [{ subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS }],
      securityGroup: props.eksSecurityGroup,
      defaultCapacity: 0,
      endpointAccess: eks.EndpointAccess.PUBLIC_AND_PRIVATE,
      albController: {
        version: eks.AlbControllerVersion.V2_8_2,
      },
    });

    // Allow EKS cluster SG to access Neptune and OpenSearch
    // Use CfnSecurityGroupIngress to avoid cross-stack circular dependency
    const clusterSgId = this.cluster.clusterSecurityGroup.securityGroupId;
    new ec2.CfnSecurityGroupIngress(this, 'NeptuneFromClusterSg', {
      groupId: props.neptuneSecurityGroup.securityGroupId,
      ipProtocol: 'tcp',
      fromPort: 8182,
      toPort: 8182,
      sourceSecurityGroupId: clusterSgId,
      description: 'Allow Neptune access from EKS cluster SG',
    });
    new ec2.CfnSecurityGroupIngress(this, 'OpenSearchFromClusterSg', {
      groupId: props.opensearchSecurityGroup.securityGroupId,
      ipProtocol: 'tcp',
      fromPort: 443,
      toPort: 443,
      sourceSecurityGroupId: clusterSgId,
      description: 'Allow OpenSearch access from EKS cluster SG',
    });

    // Managed Node Group
    this.cluster.addNodegroupCapacity('WorkerNodes', {
      instanceTypes: [new ec2.InstanceType(props.instanceType)],
      minSize: props.minSize,
      maxSize: props.maxSize,
      desiredSize: props.desiredSize,
      subnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      amiType: eks.NodegroupAmiType.AL2023_X86_64_STANDARD,
    });

    // =========================================
    // Namespace
    // =========================================

    const namespace = this.cluster.addManifest('AppNamespace', {
      apiVersion: 'v1',
      kind: 'Namespace',
      metadata: { name: RESOURCE_NAMES.EKS_NAMESPACE },
    });

    // =========================================
    // IRSA: FastAPI Service Account
    // =========================================

    this.fastapiServiceAccount = this.cluster.addServiceAccount('FastApiSA', {
      name: RESOURCE_NAMES.FASTAPI_SA,
      namespace: RESOURCE_NAMES.EKS_NAMESPACE,
    });
    this.fastapiServiceAccount.node.addDependency(namespace);

    // S3 access
    props.parsedBucket.grantReadWrite(this.fastapiServiceAccount);
    props.mockCacheBucket.grantReadWrite(this.fastapiServiceAccount);

    // Neptune — full access (IAM auth uses cluster resource ID, wildcard avoids mismatch)
    this.fastapiServiceAccount.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ['neptune-db:*'],
        resources: [
          `arn:aws:neptune-db:${this.region}:${this.account}:*`,
        ],
      }),
    );

    // OpenSearch Serverless — full API access
    this.fastapiServiceAccount.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ['aoss:*'],
        resources: [props.opensearchCollectionArn],
      }),
    );

    // Bedrock — invoke all models
    this.fastapiServiceAccount.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
        ],
        resources: ['*'],
      }),
    );

    // =========================================
    // IRSA: Next.js Service Account
    // =========================================

    this.nextjsServiceAccount = this.cluster.addServiceAccount('NextJsSA', {
      name: RESOURCE_NAMES.NEXTJS_SA,
      namespace: RESOURCE_NAMES.EKS_NAMESPACE,
    });
    this.nextjsServiceAccount.node.addDependency(namespace);

    // Next.js only needs mock cache read access
    props.mockCacheBucket.grantRead(this.nextjsServiceAccount);

    // =========================================
    // ConfigMap (env vars for application pods)
    // =========================================

    const configMap = this.cluster.addManifest('AppConfigMap', {
      apiVersion: 'v1',
      kind: 'ConfigMap',
      metadata: {
        name: 'app-config',
        namespace: RESOURCE_NAMES.EKS_NAMESPACE,
      },
      data: {
        NEPTUNE_ENDPOINT: props.neptuneClusterEndpoint,
        NEPTUNE_PORT: props.neptuneClusterPort,
        OPENSEARCH_ENDPOINT: props.opensearchCollectionEndpoint,
        PARSED_BUCKET: props.parsedBucket.bucketName,
        MOCK_CACHE_BUCKET: props.mockCacheBucket.bucketName,
        AWS_REGION: this.region,
        BEDROCK_REGION: this.region,
        GRAPHRAG_BACKEND_URL: `http://fastapi.${RESOURCE_NAMES.EKS_NAMESPACE}.svc.cluster.local:80`,
      },
    });
    configMap.node.addDependency(namespace);

    // =========================================
    // K8s Deployments
    // =========================================

    // FastAPI Deployment
    const fastApiDeployment = this.cluster.addManifest('FastApiDeployment', {
      apiVersion: 'apps/v1',
      kind: 'Deployment',
      metadata: {
        name: 'fastapi',
        namespace: RESOURCE_NAMES.EKS_NAMESPACE,
      },
      spec: {
        replicas: 2,
        selector: { matchLabels: { app: 'fastapi' } },
        template: {
          metadata: { labels: { app: 'fastapi' } },
          spec: {
            serviceAccountName: RESOURCE_NAMES.FASTAPI_SA,
            containers: [
              {
                name: 'fastapi',
                image: `${this.account}.dkr.ecr.${this.region}.amazonaws.com/${RESOURCE_NAMES.BACKEND_REPO}:latest`,
                ports: [{ containerPort: 8000 }],
                envFrom: [{ configMapRef: { name: 'app-config' } }],
                resources: {
                  requests: { cpu: '500m', memory: '512Mi' },
                  limits: { cpu: '1000m', memory: '1Gi' },
                },
              },
            ],
          },
        },
      },
    });
    fastApiDeployment.node.addDependency(namespace);

    // FastAPI Service
    const fastApiService = this.cluster.addManifest('FastApiService', {
      apiVersion: 'v1',
      kind: 'Service',
      metadata: {
        name: 'fastapi',
        namespace: RESOURCE_NAMES.EKS_NAMESPACE,
      },
      spec: {
        selector: { app: 'fastapi' },
        ports: [{ port: 80, targetPort: 8000, protocol: 'TCP' }],
        type: 'ClusterIP',
      },
    });
    fastApiService.node.addDependency(namespace);

    // Next.js Deployment
    const nextjsDeployment = this.cluster.addManifest('NextjsDeployment', {
      apiVersion: 'apps/v1',
      kind: 'Deployment',
      metadata: {
        name: 'nextjs',
        namespace: RESOURCE_NAMES.EKS_NAMESPACE,
      },
      spec: {
        replicas: 2,
        selector: { matchLabels: { app: 'nextjs' } },
        template: {
          metadata: { labels: { app: 'nextjs' } },
          spec: {
            serviceAccountName: RESOURCE_NAMES.NEXTJS_SA,
            containers: [
              {
                name: 'nextjs',
                image: `${this.account}.dkr.ecr.${this.region}.amazonaws.com/${RESOURCE_NAMES.FRONTEND_REPO}:latest`,
                ports: [{ containerPort: 3000 }],
                envFrom: [{ configMapRef: { name: 'app-config' } }],
                resources: {
                  requests: { cpu: '250m', memory: '256Mi' },
                  limits: { cpu: '500m', memory: '512Mi' },
                },
              },
            ],
          },
        },
      },
    });
    nextjsDeployment.node.addDependency(namespace);

    // Next.js Service
    const nextjsService = this.cluster.addManifest('NextjsService', {
      apiVersion: 'v1',
      kind: 'Service',
      metadata: {
        name: 'nextjs',
        namespace: RESOURCE_NAMES.EKS_NAMESPACE,
      },
      spec: {
        selector: { app: 'nextjs' },
        ports: [{ port: 80, targetPort: 3000, protocol: 'TCP' }],
        type: 'ClusterIP',
      },
    });
    nextjsService.node.addDependency(namespace);

    // ALB Ingress
    const appIngress = this.cluster.addManifest('AppIngress', {
      apiVersion: 'networking.k8s.io/v1',
      kind: 'Ingress',
      metadata: {
        name: 'app-ingress',
        namespace: RESOURCE_NAMES.EKS_NAMESPACE,
        annotations: {
          'alb.ingress.kubernetes.io/scheme': 'internet-facing',
          'alb.ingress.kubernetes.io/target-type': 'ip',
          'alb.ingress.kubernetes.io/listen-ports': '[{"HTTP": 80}]',
        },
      },
      spec: {
        ingressClassName: 'alb',
        rules: [
          {
            http: {
              paths: [
                {
                  path: '/v1',
                  pathType: 'Prefix',
                  backend: {
                    service: { name: 'fastapi', port: { number: 80 } },
                  },
                },
                {
                  path: '/',
                  pathType: 'Prefix',
                  backend: {
                    service: { name: 'nextjs', port: { number: 80 } },
                  },
                },
              ],
            },
          },
        ],
      },
    });
    appIngress.node.addDependency(namespace);

    // HPA for FastAPI
    const fastApiHpa = this.cluster.addManifest('FastApiHpa', {
      apiVersion: 'autoscaling/v2',
      kind: 'HorizontalPodAutoscaler',
      metadata: {
        name: 'fastapi-hpa',
        namespace: RESOURCE_NAMES.EKS_NAMESPACE,
      },
      spec: {
        scaleTargetRef: {
          apiVersion: 'apps/v1',
          kind: 'Deployment',
          name: 'fastapi',
        },
        minReplicas: 2,
        maxReplicas: 6,
        metrics: [
          {
            type: 'Resource',
            resource: {
              name: 'cpu',
              target: { type: 'Utilization', averageUtilization: 70 },
            },
          },
        ],
      },
    });
    fastApiHpa.node.addDependency(namespace);

    // =========================================
    // Outputs
    // =========================================

    new cdk.CfnOutput(this, 'EksClusterName', {
      value: this.cluster.clusterName,
      exportName: 'EksClusterName',
    });
    new cdk.CfnOutput(this, 'FastApiServiceAccountArn', {
      value: this.fastapiServiceAccount.role.roleArn,
      exportName: 'FastApiServiceAccountArn',
    });
    new cdk.CfnOutput(this, 'NextjsServiceAccountArn', {
      value: this.nextjsServiceAccount.role.roleArn,
      exportName: 'NextjsServiceAccountArn',
    });
    new cdk.CfnOutput(this, 'EksClusterEndpoint', {
      value: this.cluster.clusterEndpoint,
    });
    new cdk.CfnOutput(this, 'BackendRepoUri', {
      value: this.backendRepo.repositoryUri,
      exportName: 'BackendRepoUri',
    });
    new cdk.CfnOutput(this, 'FrontendRepoUri', {
      value: this.frontendRepo.repositoryUri,
      exportName: 'FrontendRepoUri',
    });
  }
}
