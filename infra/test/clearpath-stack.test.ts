import assert from "node:assert/strict";
import { test } from "node:test";
import { App, aws_lambda as lambda } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import {
  ClearPathConfig,
  ClearPathStack,
  readConfig,
} from "../lib/clearpath-stack";

const config: ClearPathConfig = {
  modelId: "amazon.nova-lite-v1:0",
  additionalModelArns: [],
  frontendOrigins: ["http://localhost:5173"],
  localBundling: false,
  enableSemanticMemory: true,
  memoryProcessingRegionConfirmed: true,
  memoryEventExpiryDays: 7,
};

function fixture(overrides: Partial<ClearPathConfig> = {}) {
  const app = new App();
  const stack = new ClearPathStack(app, "ClearPathTest", {
    env: { account: "123456789012", region: "us-east-1" },
    config: { ...config, ...overrides },
    backendCode: lambda.Code.fromInline(
      "def handler(event, context): return {}",
    ),
  });
  return Template.fromStack(stack);
}

test("stack protects application routes and leaves only CORS preflight unauthenticated", () => {
  const template = fixture();
  template.hasResourceProperties("AWS::ApiGatewayV2::Authorizer", {
    AuthorizerType: "JWT",
    IdentitySource: ["$request.header.Authorization"],
    JwtConfiguration: {
      Audience: Match.anyValue(),
      Issuer: Match.anyValue(),
    },
  });
  template.hasResourceProperties("AWS::ApiGatewayV2::Route", {
    RouteKey: "$default",
    AuthorizationType: "JWT",
    AuthorizationScopes: ["clearpath/review"],
  });
  template.hasResourceProperties("AWS::ApiGatewayV2::Route", {
    RouteKey: "OPTIONS /{proxy+}",
    AuthorizationType: "NONE",
    AuthorizationScopes: Match.absent(),
  });
  assert.match(JSON.stringify(template.toJSON()), /cognito-idp.*us-east-1/);
});

test("browser auth is invite-only, secretless, and authorization-code based", () => {
  const template = fixture();
  template.hasResource("AWS::Cognito::UserPool", {
    DeletionPolicy: "Retain",
    Properties: Match.objectLike({
      AdminCreateUserConfig: { AllowAdminCreateUserOnly: true },
      DeletionProtection: "ACTIVE",
      MfaConfiguration: "OPTIONAL",
      UsernameAttributes: ["email"],
    }),
  });
  template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
    GenerateSecret: false,
    AllowedOAuthFlows: ["code"],
    AllowedOAuthFlowsUserPoolClient: true,
    AllowedOAuthScopes: Match.arrayWith(["openid", "email"]),
    EnableTokenRevocation: true,
  });
  template.resourceCountIs("AWS::Cognito::UserPoolDomain", 1);
  assert.match(JSON.stringify(template.toJSON()), /clearpath.*review/);
});

test("semantic Memory is provisioned but runtime access stays opt-in", () => {
  const template = fixture();
  template.hasResourceProperties("AWS::BedrockAgentCore::Memory", {
    EventExpiryDuration: 7,
    MemoryStrategies: Match.anyValue(),
  });
  const rendered = JSON.stringify(template.toJSON());
  for (const action of [
    "bedrock-agentcore:CreateEvent",
    "bedrock-agentcore:RetrieveMemoryRecords",
    "bedrock-agentcore:DeleteMemoryRecord",
  ]) {
    assert.equal(rendered.includes(action), false);
  }
  assert.equal(rendered.includes("AGENTCORE_MEMORY_ID"), false);
});

test("a strategy ID wires Memory into both Lambdas with scoped runtime access", () => {
  const strategyId = "ApprovedLessons-a1b2c3d4e5";
  const template = fixture({ agentcoreMemoryStrategyId: strategyId });
  template.resourcePropertiesCountIs(
    "AWS::Lambda::Function",
    {
      Environment: {
        Variables: Match.objectLike({
          AGENTCORE_MEMORY_ID: Match.anyValue(),
          AGENTCORE_MEMORY_STRATEGY_ID: strategyId,
        }),
      },
    },
    2,
  );
  const rendered = JSON.stringify(template.toJSON());
  assert.equal(rendered.includes("bedrock-agentcore:CreateEvent"), true);
  assert.equal(
    rendered.includes("bedrock-agentcore:RetrieveMemoryRecords"),
    true,
  );
  assert.equal(rendered.includes("bedrock-agentcore:DeleteEvent"), false);
  assert.equal(
    rendered.includes("bedrock-agentcore:DeleteMemoryRecord"),
    false,
  );
});

test("runtime Memory requires enabled, region-confirmed semantic processing", () => {
  const strategyId = "ApprovedLessons-a1b2c3d4e5";
  for (const overrides of [
    { enableSemanticMemory: false },
    { memoryProcessingRegionConfirmed: false },
  ]) {
    assert.throws(
      () => fixture({ agentcoreMemoryStrategyId: strategyId, ...overrides }),
      /requires enabled, region-confirmed semantic Memory/,
    );
  }
});

test("stack rejects deployment outside us-east-1", () => {
  const app = new App();
  assert.throws(
    () =>
      new ClearPathStack(app, "WrongRegion", {
        env: { account: "123456789012", region: "us-west-2" },
        config,
        backendCode: lambda.Code.fromInline("x"),
      }),
    /restricted to us-east-1/,
  );
});

test("context rejects plaintext non-loopback frontend origins", () => {
  const app = new App({
    context: { frontendOrigins: JSON.stringify(["http://example.com"]) },
  });
  assert.throws(
    () => readConfig(app),
    /exact HTTPS origins \(or loopback HTTP origins\)/,
  );
});

test("context defaults Memory and semantic extraction on but requires confirmation", () => {
  const app = new App({ context: {} });
  const parsed = readConfig(app);
  assert.equal(parsed.enableSemanticMemory, true);
  assert.equal(parsed.memoryProcessingRegionConfirmed, false);
  assert.equal(parsed.memoryEventExpiryDays, 7);
  assert.equal(parsed.agentcoreMemoryStrategyId, undefined);
  assert.equal("allowUnauthenticatedApi" in parsed, false);
});
