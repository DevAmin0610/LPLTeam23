import {
  ArnFormat,
  Names,
  RemovalPolicy,
  Stack,
  Token,
  aws_bedrockagentcore as agentcore,
  aws_iam as iam,
} from "aws-cdk-lib";
import { Construct } from "constructs";

export interface ClearPathMemoryProps {
  /**
   * Reference a memory ID in this stack's account and region without a lookup.
   * No resource is created or updated: retention, strategies, encryption, and
   * processing regions of an import must be checked by its owner separately.
   */
  readonly existingMemoryId?: string;
  /** Add the built-in semantic strategy to a new memory. Defaults to false. */
  readonly enableSemanticMemory?: boolean;
  /**
   * Explicit confirmation that the service's processing regions are authorized.
   * Required when enableSemanticMemory is true, including for imports. This is
   * an acknowledgement, NOT a setting that pins inference to us-east-1. AWS may
   * process US built-in strategies in us-east-1, us-east-2, or us-west-2. Leave
   * semantic memory disabled under the workshop's us-east-1-only restriction
   * unless the processing constraints have been resolved and approved.
   * @see https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/cross-region-inference.html
   */
  readonly memoryProcessingRegionConfirmed?: boolean;
  /**
   * Raw event expiry for a new memory: integer days from 3 through 365, default 7.
   * Does not expire extracted records. Changes affect only newly written events.
   * Ignored for imports, whose retention remains externally managed.
   */
  readonly eventExpiryDays?: number;
  /**
   * Boundary for roles owned by this construct, not for grant recipients.
   * Currently no roles are created: the built-in strategy needs no customer
   * model execution role. Custom strategies/model overrides are not supported.
   */
  readonly permissionsBoundary?: iam.IManagedPolicy;
}

/**
 * Infrastructure only for sanitized, explicitly approved advisory lessons.
 * No backend wiring, AgentCore Runtime, model grants, or automatic ingestion.
 *
 * Namespaces organize records; they do not authorize access. The future caller
 * must enforce actor/scope isolation, approval, provenance, applicable rule
 * versions, and revocation in the authoritative application store. Neither
 * strategy descriptions nor grant helpers implement these controls.
 *
 * @see https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-memory.html
 * @see https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-configuring-built-in-strategies.html
 * @see https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-custom-strategy.html
 */
export class ClearPathMemory extends Construct {
  public readonly memoryId: string;
  public readonly memoryArn: string;

  constructor(scope: Construct, id: string, props: ClearPathMemoryProps = {}) {
    super(scope, id);
    const stack = Stack.of(this);
    if (!Token.isUnresolved(stack.region) && stack.region !== "us-east-1") {
      throw new Error("ClearPath Memory is restricted to us-east-1.");
    }
    if (
      props.enableSemanticMemory === true &&
      props.memoryProcessingRegionConfirmed !== true
    ) {
      throw new Error(
        "Semantic memory requires memoryProcessingRegionConfirmed=true after authorized review of AWS cross-region processing; this flag does not enforce us-east-1-only inference.",
      );
    }

    const eventExpiryDays = props.eventExpiryDays ?? 7;
    if (
      !Number.isInteger(eventExpiryDays) ||
      eventExpiryDays < 3 ||
      eventExpiryDays > 365
    ) {
      throw new Error("eventExpiryDays must be an integer from 3 through 365.");
    }
    if (props.permissionsBoundary) {
      iam.PermissionsBoundary.of(this).apply(props.permissionsBoundary);
    }

    if (props.existingMemoryId !== undefined) {
      if (
        !Token.isUnresolved(props.existingMemoryId) &&
        !/^[a-zA-Z][a-zA-Z0-9_-]{0,99}-[a-zA-Z0-9]{10}$/.test(
          props.existingMemoryId,
        )
      ) {
        throw new Error(
          "existingMemoryId must be an AgentCore memory ID, not an ARN, name, or wildcard.",
        );
      }
      this.memoryId = props.existingMemoryId;
      this.memoryArn = stack.formatArn({
        service: "bedrock-agentcore",
        resource: "memory",
        resourceName: this.memoryId,
        arnFormat: ArnFormat.SLASH_RESOURCE_NAME,
      });
      return;
    }

    const memory = new agentcore.CfnMemory(this, "Resource", {
      name: `ClearPath_${Names.uniqueResourceName(this, {
        maxLength: 38,
        allowedSpecialCharacters: "_",
        separator: "_",
      })}`,
      description:
        "ClearPath synthetic, sanitized, approved advisory lessons; not policy or case evidence.",
      eventExpiryDuration: eventExpiryDays,
      // Built-in strategies use service-managed models. Do not invent a model
      // ARN or execution role; overrides require a separate reviewed design.
      memoryStrategies:
        props.enableSemanticMemory === true
          ? [
              {
                semanticMemoryStrategy: {
                  name: "ApprovedLessons",
                  description:
                    "Advisory lessons only; caller must sanitize, authorize, and approve before ingestion.",
                  namespaceTemplates: [
                    "/clearpath/lessons/{memoryStrategyId}/{actorId}/",
                  ],
                },
              },
            ]
          : undefined,
    });
    memory.applyRemovalPolicy(RemovalPolicy.RETAIN);
    // CloudFormation Ref returns the ARN, not the data-plane memory ID.
    this.memoryId = memory.attrMemoryId;
    this.memoryArn = memory.attrMemoryArn;
  }

  /**
   * Read/search extracted records only, not raw events or memory configuration.
   * Grants cover this entire memory; callers must enforce lesson eligibility
   * and access isolation before returning or using any retrieved record.
   */
  public grantRetrieval(grantee: iam.IGrantable): iam.Grant {
    return this.grant(grantee, [
      "bedrock-agentcore:GetMemoryRecord",
      "bedrock-agentcore:ListMemoryRecords",
      "bedrock-agentcore:RetrieveMemoryRecords",
    ]);
  }

  /**
   * Write events for asynchronous extraction; no direct record writes or reads.
   * Call only after sanitization and explicit authorized lesson approval exist.
   * An imported memory may already have active extraction strategies.
   */
  public grantIngestion(grantee: iam.IGrantable): iam.Grant {
    return this.grant(grantee, ["bedrock-agentcore:CreateEvent"]);
  }

  /**
   * Delete known source events and extracted records, not the memory resource.
   * This is permission, not a revocation workflow: record IDs/provenance must be
   * tracked externally, and retrieval must reject revoked lessons even while
   * deletion or asynchronous extraction is pending. Event expiry/deletion alone
   * must not be treated as deletion of all derived knowledge.
   */
  public grantRevocation(grantee: iam.IGrantable): iam.Grant {
    return this.grant(grantee, [
      "bedrock-agentcore:DeleteEvent",
      "bedrock-agentcore:DeleteMemoryRecord",
    ]);
  }

  private grant(grantee: iam.IGrantable, actions: string[]): iam.Grant {
    // These actions authorize against the memory ARN, not record/event ARNs.
    // https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html
    return iam.Grant.addToPrincipal({
      grantee,
      actions,
      resourceArns: [this.memoryArn],
    });
  }
}
