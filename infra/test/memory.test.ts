import assert from "node:assert/strict";
import { test } from "node:test";
import { App, CfnParameter, Stack, aws_iam as iam } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { ClearPathMemory, ClearPathMemoryProps } from "../lib/memory";

const existingMemoryId = "ClearPathLessons-a1b2c3d4e5";

function fixture(props: ClearPathMemoryProps = {}) {
  const stack = new Stack(new App(), "MemoryTest", {
    env: { account: "123456789012", region: "us-east-1" },
  });
  const memory = new ClearPathMemory(stack, "Lessons", props);
  return { stack, memory };
}

test("default creates only retained Memory with seven-day events and no model processing", () => {
  const { stack, memory } = fixture();
  const template = Template.fromStack(stack);
  const resources = template.findResources("AWS::BedrockAgentCore::Memory");
  assert.equal(Object.keys(resources).length, 1);
  const [logicalId, resource] = Object.entries(resources)[0];
  assert.deepEqual(Object.keys(template.toJSON().Resources), [logicalId]);
  assert.equal(resource.DeletionPolicy, "Retain");
  assert.equal(resource.UpdateReplacePolicy, "Retain");
  template.hasResourceProperties("AWS::BedrockAgentCore::Memory", {
    Name: Match.stringLikeRegexp("^[A-Za-z][A-Za-z0-9_]{0,47}$"),
    EventExpiryDuration: 7,
    MemoryStrategies: Match.absent(),
    MemoryExecutionRoleArn: Match.absent(),
    EncryptionKeyArn: Match.absent(),
    StreamDeliveryResources: Match.absent(),
  });
  assert.deepEqual(stack.resolve(memory.memoryId), {
    "Fn::GetAtt": [logicalId, "MemoryId"],
  });
  assert.deepEqual(stack.resolve(memory.memoryArn), {
    "Fn::GetAtt": [logicalId, "MemoryArn"],
  });
});

test("semantic extraction requires explicit processing-region confirmation", () => {
  for (const memoryProcessingRegionConfirmed of [undefined, false]) {
    for (const imported of [false, true]) {
      assert.throws(
        () =>
          fixture({
            enableSemanticMemory: true,
            memoryProcessingRegionConfirmed,
            existingMemoryId: imported ? existingMemoryId : undefined,
          }),
        /memoryProcessingRegionConfirmed=true.*cross-region/,
      );
    }
  }
});

test("confirmation alone does not enable semantic extraction", () => {
  for (const enableSemanticMemory of [undefined, false]) {
    const { stack } = fixture({
      enableSemanticMemory,
      memoryProcessingRegionConfirmed: true,
    });
    Template.fromStack(stack).hasResourceProperties(
      "AWS::BedrockAgentCore::Memory",
      { MemoryStrategies: Match.absent() },
    );
  }
});

test("confirmed semantic Memory uses one built-in strategy with actor-scoped organization and no IAM role", () => {
  const { stack } = fixture({
    enableSemanticMemory: true,
    memoryProcessingRegionConfirmed: true,
  });
  const template = Template.fromStack(stack);
  template.hasResourceProperties("AWS::BedrockAgentCore::Memory", {
    EventExpiryDuration: 7,
    MemoryStrategies: [
      {
        SemanticMemoryStrategy: {
          Name: "ApprovedLessons",
          Description: Match.anyValue(),
          NamespaceTemplates: [
            "/clearpath/lessons/{memoryStrategyId}/{actorId}/",
          ],
        },
      },
    ],
    MemoryExecutionRoleArn: Match.absent(),
  });
  assert.equal(Object.keys(template.toJSON().Resources).length, 1);
});

test("explicit event expiry supports the documented endpoints and overrides the default", () => {
  for (const eventExpiryDays of [3, 14, 365]) {
    const { stack } = fixture({ eventExpiryDays });
    Template.fromStack(stack).hasResourceProperties(
      "AWS::BedrockAgentCore::Memory",
      { EventExpiryDuration: eventExpiryDays },
    );
  }
});

test("event expiry rejects out-of-range, fractional, and non-finite values", () => {
  for (const eventExpiryDays of [0, 2, 366, -7, 3.5, NaN, Infinity]) {
    assert.throws(
      () => fixture({ eventExpiryDays }),
      /integer from 3 through 365/,
    );
  }
});

test("import references the exact memory in the stack account/region without creating or updating resources", () => {
  for (const props of [
    { existingMemoryId },
    {
      existingMemoryId,
      enableSemanticMemory: true,
      memoryProcessingRegionConfirmed: true,
      eventExpiryDays: 14,
    },
  ]) {
    const { stack, memory } = fixture(props);
    assert.equal(memory.memoryId, existingMemoryId);
    assert.deepEqual(stack.resolve(memory.memoryArn), {
      "Fn::Join": [
        "",
        [
          "arn:",
          { Ref: "AWS::Partition" },
          `:bedrock-agentcore:us-east-1:123456789012:memory/${existingMemoryId}`,
        ],
      ],
    });
    assert.deepEqual(Template.fromStack(stack).toJSON().Resources ?? {}, {});
  }
});

test("import rejects empty IDs, names, ARNs, paths, and IAM wildcards", () => {
  for (const invalidId of [
    "",
    " ",
    "ClearPathLessons",
    "ClearPathLessons-short",
    "ClearPathLessons-a1b2c3d4e5\n",
    ` ${existingMemoryId}`,
    `${existingMemoryId} `,
    `arn:aws:bedrock-agentcore:us-east-1:123456789012:memory/${existingMemoryId}`,
    `${existingMemoryId}/records`,
    "ClearPath*-a1b2c3d4e5",
    "ClearPath?-a1b2c3d4e5",
  ]) {
    assert.throws(
      () => fixture({ existingMemoryId: invalidId }),
      /existingMemoryId must be an AgentCore memory ID/,
    );
  }
});

test("unresolved memory IDs remain CloudFormation references, with no lookups", () => {
  const stack = new Stack(new App(), "ParameterizedMemory");
  const parameter = new CfnParameter(stack, "ExistingMemoryId", {
    type: "String",
    allowedPattern: "[a-zA-Z][a-zA-Z0-9_-]{0,99}-[a-zA-Z0-9]{10}",
  });
  const memory = new ClearPathMemory(stack, "Lessons", {
    existingMemoryId: parameter.valueAsString,
  });
  assert.deepEqual(stack.resolve(memory.memoryId), { Ref: "ExistingMemoryId" });
  assert.deepEqual(stack.resolve(memory.memoryArn), {
    "Fn::Join": [
      "",
      [
        "arn:",
        { Ref: "AWS::Partition" },
        ":bedrock-agentcore:",
        { Ref: "AWS::Region" },
        ":",
        { Ref: "AWS::AccountId" },
        ":memory/",
        { Ref: "ExistingMemoryId" },
      ],
    ],
  });
  const reader = new iam.Role(stack, "Reader", {
    assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  });
  memory.grantRetrieval(reader);
  Template.fromStack(stack).resourceCountIs("AWS::BedrockAgentCore::Memory", 0);
});

test("concrete regions outside the workshop restriction are rejected for creation and import", () => {
  for (const props of [{}, { existingMemoryId }]) {
    const stack = new Stack(new App(), "WrongRegion", {
      env: { account: "123456789012", region: "us-west-2" },
    });
    assert.throws(
      () => new ClearPathMemory(stack, "Lessons", props),
      /restricted to us-east-1/,
    );
  }
});

test("generated names are valid, unique, and stable for long or numeric construct paths", () => {
  function names() {
    const stack = new Stack(new App(), "123-Memory-Test", {
      stackName: "MemoryTest",
    });
    new ClearPathMemory(stack, "1-lesson-store".repeat(10));
    new ClearPathMemory(stack, "2-lesson-store".repeat(10));
    return Object.values(
      Template.fromStack(stack).findResources("AWS::BedrockAgentCore::Memory"),
    ).map((resource) => resource.Properties.Name as string);
  }
  const generated = names();
  assert.equal(new Set(generated).size, 2);
  for (const name of generated) {
    assert.match(name, /^[A-Za-z][A-Za-z0-9_]{0,47}$/);
  }
  assert.deepEqual(names(), generated);
});

test("permissions boundary creates no unnecessary role and does not mutate sibling grant recipients", () => {
  const stack = new Stack(new App(), "BoundaryTest");
  const boundary = iam.ManagedPolicy.fromManagedPolicyArn(
    stack,
    "Boundary",
    "arn:aws:iam::123456789012:policy/WorkshopBoundary",
  );
  const memory = new ClearPathMemory(stack, "Lessons", {
    enableSemanticMemory: true,
    memoryProcessingRegionConfirmed: true,
    permissionsBoundary: boundary,
  });
  const reader = new iam.Role(stack, "Reader", {
    assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  });
  memory.grantRetrieval(reader);
  const template = Template.fromStack(stack);
  template.resourceCountIs("AWS::IAM::Role", 1);
  template.resourceCountIs("AWS::IAM::ManagedPolicy", 0);
  template.hasResourceProperties("AWS::IAM::Role", {
    PermissionsBoundary: Match.absent(),
  });
  template.hasResourceProperties("AWS::BedrockAgentCore::Memory", {
    MemoryExecutionRoleArn: Match.absent(),
  });
});

const grants = [
  {
    method: "grantRetrieval",
    actions: [
      "bedrock-agentcore:GetMemoryRecord",
      "bedrock-agentcore:ListMemoryRecords",
      "bedrock-agentcore:RetrieveMemoryRecords",
    ],
  },
  {
    method: "grantIngestion",
    actions: ["bedrock-agentcore:CreateEvent"],
  },
  {
    method: "grantRevocation",
    actions: [
      "bedrock-agentcore:DeleteEvent",
      "bedrock-agentcore:DeleteMemoryRecord",
    ],
  },
] as const;

for (const imported of [false, true]) {
  for (const { method, actions } of grants) {
    test(`${method} grants only its documented actions on the exact ${imported ? "imported" : "created"} memory ARN`, () => {
      const { stack, memory } = fixture({
        existingMemoryId: imported ? existingMemoryId : undefined,
      });
      const role = new iam.Role(stack, "Caller", {
        assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      });
      const grant = memory[method](role);
      assert.equal(grant.success, true);
      const template = Template.fromStack(stack);
      const policies = Object.values(
        template.findResources("AWS::IAM::Policy"),
      );
      assert.equal(policies.length, 1);
      assert.deepEqual(policies[0].Properties.PolicyDocument, {
        Version: "2012-10-17",
        Statement: [
          {
            Effect: "Allow",
            Action: actions.length === 1 ? actions[0] : [...actions],
            Resource: stack.resolve(memory.memoryArn),
          },
        ],
      });
      template.resourceCountIs("AWS::IAM::Role", 1);
      template.resourceCountIs("AWS::IAM::ManagedPolicy", 0);
      template.resourceCountIs("AWS::Lambda::Function", 0);
      template.resourceCountIs("AWS::BedrockAgentCore::Runtime", 0);
    });
  }
}
