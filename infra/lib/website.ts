import {
  CfnOutput,
  Duration,
  RemovalPolicy,
  aws_cloudfront as cloudfront,
  aws_cloudfront_origins as origins,
  aws_s3 as s3,
} from "aws-cdk-lib";
import { Construct } from "constructs";

/** Private static hosting. API traffic intentionally uses the separate API URL. */
export class ClearPathWebsite extends Construct {
  public readonly bucket: s3.Bucket;
  public readonly distribution: cloudfront.Distribution;
  public readonly origin: string;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.bucket = new s3.Bucket(this, "Assets", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      removalPolicy: RemovalPolicy.RETAIN,
      autoDeleteObjects: false,
    });

    const spaRewrite = new cloudfront.Function(this, "SpaRewrite", {
      comment:
        "Rewrite extensionless browser routes to the ClearPath SPA entry point.",
      code: cloudfront.FunctionCode.fromInline(`function handler(event) {
  var request = event.request;
  if ((request.method === 'GET' || request.method === 'HEAD') &&
      request.uri !== '/api' && !request.uri.startsWith('/api/') &&
      !request.uri.substring(request.uri.lastIndexOf('/') + 1).includes('.')) {
    request.uri = '/index.html';
  }
  return request;
}`),
      runtime: cloudfront.FunctionRuntime.JS_2_0,
    });

    const indexCachePolicy = new cloudfront.CachePolicy(this, "IndexCache", {
      comment:
        "Short cache for the SPA shell so deployments become visible quickly.",
      defaultTtl: Duration.seconds(0),
      minTtl: Duration.seconds(0),
      maxTtl: Duration.minutes(5),
      enableAcceptEncodingBrotli: true,
      enableAcceptEncodingGzip: true,
    });

    const staticOrigin = origins.S3BucketOrigin.withOriginAccessControl(
      this.bucket,
    );
    this.distribution = new cloudfront.Distribution(this, "Distribution", {
      comment: "ClearPath hackathon frontend",
      defaultRootObject: "index.html",

      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
      httpVersion: cloudfront.HttpVersion.HTTP2_AND_3,
      enableIpv6: true,
      defaultBehavior: {
        origin: staticOrigin,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
        cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
        cachePolicy: indexCachePolicy,
        compress: true,
        responseHeadersPolicy:
          cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        functionAssociations: [
          {
            function: spaRewrite,
            eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,
          },
        ],
      },
      additionalBehaviors: {
        "assets/*": {
          origin: staticOrigin,
          viewerProtocolPolicy:
            cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
          cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
          cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
          compress: true,
          responseHeadersPolicy:
            cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        },
      },
    });

    this.origin = `https://${this.distribution.distributionDomainName}`;
    new CfnOutput(this, "Url", { value: this.origin });
    new CfnOutput(this, "BucketName", { value: this.bucket.bucketName });
    new CfnOutput(this, "DistributionId", {
      value: this.distribution.distributionId,
    });
  }
}
