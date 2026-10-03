import { test } from "node:test";
import { App, Stack } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { ClearPathWebsite } from "../lib/website";

function template() {
  const stack = new Stack(new App(), "WebsiteTest");
  new ClearPathWebsite(stack, "Website");
  return Template.fromStack(stack);
}

test("website uses a retained private TLS-only bucket and CloudFront OAC", () => {
  const result = template();
  result.hasResource("AWS::S3::Bucket", {
    DeletionPolicy: "Retain",
    UpdateReplacePolicy: "Retain",
    Properties: {
      BucketEncryption: Match.anyValue(),
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
    },
  });
  result.hasResourceProperties("AWS::S3::BucketPolicy", {
    PolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Effect: "Deny",
          Principal: { AWS: "*" },
          Condition: { Bool: { "aws:SecureTransport": "false" } },
        }),
      ]),
    },
  });
  result.resourceCountIs("AWS::CloudFront::OriginAccessControl", 1);
});

test("distribution is static-only, redirects to HTTPS, and applies safe SPA rewrites", () => {
  const result = template();
  result.hasResourceProperties("AWS::CloudFront::Distribution", {
    DistributionConfig: Match.objectLike({
      DefaultRootObject: "index.html",
      HttpVersion: "http2and3",
      IPV6Enabled: true,
      PriceClass: "PriceClass_100",
      DefaultCacheBehavior: Match.objectLike({
        ViewerProtocolPolicy: "redirect-to-https",
        AllowedMethods: ["GET", "HEAD", "OPTIONS"],
        Compress: true,
      }),
      CacheBehaviors: Match.arrayWith([
        Match.objectLike({
          PathPattern: "assets/*",
          ViewerProtocolPolicy: "redirect-to-https",
          AllowedMethods: ["GET", "HEAD", "OPTIONS"],
          Compress: true,
        }),
      ]),
      CustomErrorResponses: Match.absent(),
    }),
  });
  result.hasResourceProperties("AWS::CloudFront::Function", {
    FunctionCode: Match.stringLikeRegexp("index.html"),
  });
  result.resourceCountIs("AWS::CloudFront::ResponseHeadersPolicy", 0);
});
