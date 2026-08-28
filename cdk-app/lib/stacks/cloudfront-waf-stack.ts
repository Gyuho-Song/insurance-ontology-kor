import * as cdk from 'aws-cdk-lib';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';
import { Construct } from 'constructs';

export interface CloudFrontWafStackProps extends cdk.StackProps {
  readonly albDnsName: string;
  readonly originVerifyHeader: string;
  readonly originVerifySecret: string;
}

export class CloudFrontWafStack extends cdk.Stack {
  public readonly distribution: cloudfront.Distribution;

  constructor(scope: Construct, id: string, props: CloudFrontWafStackProps) {
    super(scope, id, props);

    // =========================================
    // WAF WebACL (CLOUDFRONT scope — must be us-east-1)
    // =========================================

    const webAcl = new wafv2.CfnWebACL(this, 'WebAcl', {
      name: 'ontology-demo-waf',
      scope: 'CLOUDFRONT',
      defaultAction: { allow: {} },
      visibilityConfig: {
        sampledRequestsEnabled: true,
        cloudWatchMetricsEnabled: true,
        metricName: 'OntologyDemoWebAcl',
      },
      rules: [
        // 1. AWS Common Rule Set
        {
          name: 'AWSManagedRulesCommonRuleSet',
          priority: 1,
          statement: {
            managedRuleGroupStatement: {
              vendorName: 'AWS',
              name: 'AWSManagedRulesCommonRuleSet',
              excludedRules: [
                { name: 'SizeRestrictions_BODY' },
              ],
            },
          },
          overrideAction: { none: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'AWSCommonRules',
          },
        },
        // 2. SQL Injection Protection
        {
          name: 'AWSManagedRulesSQLiRuleSet',
          priority: 2,
          statement: {
            managedRuleGroupStatement: {
              vendorName: 'AWS',
              name: 'AWSManagedRulesSQLiRuleSet',
            },
          },
          overrideAction: { none: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'AWSSQLiRules',
          },
        },
        // 3. Known Bad Inputs (Log4j, etc.)
        {
          name: 'AWSManagedRulesKnownBadInputsRuleSet',
          priority: 3,
          statement: {
            managedRuleGroupStatement: {
              vendorName: 'AWS',
              name: 'AWSManagedRulesKnownBadInputsRuleSet',
            },
          },
          overrideAction: { none: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'AWSKnownBadInputs',
          },
        },
        // 4. Amazon IP Reputation List
        {
          name: 'AWSManagedRulesAmazonIpReputationList',
          priority: 4,
          statement: {
            managedRuleGroupStatement: {
              vendorName: 'AWS',
              name: 'AWSManagedRulesAmazonIpReputationList',
            },
          },
          overrideAction: { none: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'AWSIpReputation',
          },
        },
        // 5. Rate Limiting (2000 req / 5 min per IP)
        {
          name: 'RateLimitRule',
          priority: 5,
          statement: {
            rateBasedStatement: {
              limit: 2000,
              aggregateKeyType: 'IP',
            },
          },
          action: { block: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'RateLimit',
          },
        },
        // 6. Login brute-force protection (20 req / 5 min per IP to /login or /api/auth)
        {
          name: 'LoginBruteForceProtection',
          priority: 6,
          statement: {
            rateBasedStatement: {
              limit: 20,
              aggregateKeyType: 'IP',
              scopeDownStatement: {
                orStatement: {
                  statements: [
                    {
                      byteMatchStatement: {
                        fieldToMatch: { uriPath: {} },
                        positionalConstraint: 'STARTS_WITH',
                        searchString: '/login',
                        textTransformations: [{ priority: 0, type: 'LOWERCASE' }],
                      },
                    },
                    {
                      byteMatchStatement: {
                        fieldToMatch: { uriPath: {} },
                        positionalConstraint: 'STARTS_WITH',
                        searchString: '/api/auth',
                        textTransformations: [{ priority: 0, type: 'LOWERCASE' }],
                      },
                    },
                  ],
                },
              },
            },
          },
          action: { block: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'LoginBruteForce',
          },
        },
      ],
    });

    // =========================================
    // CloudFront Distribution
    // =========================================

    const albOrigin = new origins.HttpOrigin(props.albDnsName, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      customHeaders: {
        [props.originVerifyHeader]: props.originVerifySecret,
      },
      connectionTimeout: cdk.Duration.seconds(10),
      readTimeout: cdk.Duration.seconds(60),
    });

    // Cache policy: disabled (SSR + API — no caching)
    const noCachePolicy = cloudfront.CachePolicy.CACHING_DISABLED;

    // Origin request policy: forward all viewer headers/cookies/query strings
    const allViewerExceptHost = cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER;

    this.distribution = new cloudfront.Distribution(this, 'Distribution', {
      comment: 'Ontology GraphRAG Demo',
      webAclId: webAcl.attrArn,
      defaultBehavior: {
        origin: albOrigin,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: noCachePolicy,
        originRequestPolicy: allViewerExceptHost,
      },
      additionalBehaviors: {
        // API path — no cache, allow all methods
        '/v1/*': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: noCachePolicy,
          originRequestPolicy: allViewerExceptHost,
        },
        // Next.js static assets — cache aggressively
        '/_next/static/*': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
          cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
          originRequestPolicy: allViewerExceptHost,
        },
      },
    });

    // =========================================
    // Outputs
    // =========================================

    new cdk.CfnOutput(this, 'DistributionDomainName', {
      value: this.distribution.distributionDomainName,
      description: 'CloudFront domain — use this as the public entry point',
    });
    new cdk.CfnOutput(this, 'DistributionId', {
      value: this.distribution.distributionId,
    });
    new cdk.CfnOutput(this, 'WebAclArn', {
      value: webAcl.attrArn,
    });
  }
}
