import * as path from "node:path";
import { spawnSync } from "node:child_process";
import {
  App,
  ArnFormat,
  Aws,
  CfnOutput,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
  aws_apigatewayv2 as apigw,
  aws_apigatewayv2_authorizers as authorizers,
  aws_apigatewayv2_integrations as integrations,
  aws_bedrock as bedrock,
  aws_cognito as cognito,
  aws_dynamodb as dynamodb,
  aws_iam as iam,
  aws_lambda as lambda,
  aws_logs as logs,
  aws_s3 as s3,
  aws_sqs as sqs,
  aws_lambda_destinations as destinations,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import { ClearPathMemory } from "./memory";
import { ClearPathWebsite } from "./website";

export interface ClearPathConfig {
  existingBucketName?: string;
  existingTableName?: string;
  guardrailId?: string;
  guardrailVersion?: string;
  modelId: string;
  /** Exact additional model ARNs required by a cross-region inference profile. */
  additionalModelArns: string[];
  frontendOrigins: string[];
  localBundling: boolean;
  apiFunctionName?: string;
  workerFunctionName?: string;
  authDomainPrefix?: string;
  permissionsBoundaryArn?: string;
  existingMemoryId?: string;
  enableSemanticMemory: boolean;
  memoryProcessingRegionConfirmed: boolean;
  memoryEventExpiryDays: number;
}

function optional(app: App, name: string): string | undefined {
  const value = app.node.tryGetContext(name);
  if (value === undefined || value === "") return undefined;
  if (typeof value !== "string" || !value.trim())
    throw new Error(`Invalid context: ${name}`);
  return value.trim();
}

function flag(app: App, name: string, fallback = false): boolean {
  const value = app.node.tryGetContext(name);
  if (value === undefined) return fallback;
  if (value === false || value === "false") return false;
  if (value === true || value === "true") return true;
  throw new Error(`Invalid boolean context: ${name}`);
}

function integer(app: App, name: string, fallback: number): number {
  const raw = app.node.tryGetContext(name);
  const value = raw === undefined ? fallback : Number(raw);
  if (!Number.isInteger(value))
    throw new Error(`Invalid integer context: ${name}`);
  return value;
}

function stringList(app: App, name: string, fallback: string[]): string[] {
  const raw = app.node.tryGetContext(name);
  const value = typeof raw === "string" ? JSON.parse(raw) : (raw ?? fallback);
  if (
    !Array.isArray(value) ||
    !value.every((v) => typeof v === "string" && v.length > 0)
  ) {
    throw new Error(`Invalid array context: ${name}`);
  }
  return value;
}

export function readConfig(app: App): ClearPathConfig {
  const guardrailId = optional(app, "guardrailId");
  const guardrailVersion = optional(app, "guardrailVersion");
  if (Boolean(guardrailId) !== Boolean(guardrailVersion)) {
    throw new Error(
      "Supply both guardrailId and guardrailVersion, or neither to create a guardrail.",
    );
  }
  if (guardrailVersion && !/^[1-9][0-9]*$/.test(guardrailVersion)) {
    throw new Error("Use a published numeric guardrailVersion, not DRAFT.");
  }
  const frontendOrigins = stringList(app, "frontendOrigins", [
    "http://localhost:5173",
  ]);
  for (const origin of frontendOrigins) {
    const url = new URL(origin);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.origin !== origin ||
      origin.includes("*")
    ) {
      throw new Error(
        "frontendOrigins must contain exact HTTP(S) origins without trailing slashes.",
      );
    }
  }
  const additionalModelArns = stringList(app, "additionalModelArns", []);
  if (
    additionalModelArns.some(
      (arn) =>
        !/^arn:[^:]+:bedrock:[^:]+:[^:]*:[^*]+$/.test(arn) || arn.includes("*"),
    )
  ) {
    throw new Error(
      "additionalModelArns must be exact Bedrock ARNs, not wildcards.",
    );
  }
  return {
    existingBucketName: optional(app, "existingBucketName"),
    existingTableName: optional(app, "existingTableName"),
    guardrailId,
    guardrailVersion,
    modelId: optional(app, "modelId") ?? "amazon.nova-lite-v1:0",
    additionalModelArns,
    frontendOrigins,
    localBundling: flag(app, "localBundling"),
    apiFunctionName: optional(app, "apiFunctionName"),
    workerFunctionName: optional(app, "workerFunctionName"),
    authDomainPrefix: optional(app, "authDomainPrefix"),
    permissionsBoundaryArn: optional(app, "permissionsBoundaryArn"),
    existingMemoryId: optional(app, "existingMemoryId"),
    enableSemanticMemory: flag(app, "enableSemanticMemory", true),
    memoryProcessingRegionConfirmed: flag(
      app,
      "memoryProcessingRegionConfirmed",
    ),
    memoryEventExpiryDays: integer(app, "memoryEventExpiryDays", 7),
  };
}

export interface ClearPathStackProps extends StackProps {
  config: ClearPathConfig;
  /** Test-only injection: the CLI always packages the real backend. */
  backendCode?: lambda.Code;
}

export class ClearPathStack extends Stack {
  constructor(scope: Construct, id: string, props: ClearPathStackProps) {
    super(scope, id, props);
    const config = props.config;
    if (this.region !== "us-east-1" && this.region !== Aws.REGION) {
      throw new Error("ClearPath AWS deployment is restricted to us-east-1.");
    }

    const permissionsBoundary = config.permissionsBoundaryArn
      ? iam.ManagedPolicy.fromManagedPolicyArn(
          this,
          "WorkshopPermissionsBoundary",
          config.permissionsBoundaryArn,
        )
      : undefined;
    if (permissionsBoundary) {
      iam.PermissionsBoundary.of(this).apply(permissionsBoundary);
    }

    const website = new ClearPathWebsite(this, "Website");
    const frontendOrigins = Array.from(
      new Set([...config.frontendOrigins, website.origin]),
    );

    const userPool = new cognito.UserPool(this, "UserPool", {
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      autoVerify: { email: true },
      signInCaseSensitive: false,
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      mfa: cognito.Mfa.OPTIONAL,
      mfaSecondFactor: { otp: true, sms: false },
      passwordPolicy: {
        minLength: 12,
        requireDigits: true,
        requireLowercase: true,
        requireUppercase: true,
        requireSymbols: true,
        tempPasswordValidity: Duration.days(3),
      },
      featurePlan: cognito.FeaturePlan.LITE,
      deletionProtection: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const reviewScope = new cognito.ResourceServerScope({
      scopeName: "review",
      scopeDescription: "Access the authenticated ClearPath review API.",
    });
    const resourceServer = userPool.addResourceServer("ApiResourceServer", {
      identifier: "clearpath",
      scopes: [reviewScope],
    });
    const callbackUrls = Array.from(
      new Set([...config.frontendOrigins, website.origin]),
    );
    const userPoolClient = userPool.addClient("BrowserClient", {
      generateSecret: false,
      preventUserExistenceErrors: true,
      enableTokenRevocation: true,
      authFlows: { userSrp: true },
      accessTokenValidity: Duration.hours(1),
      idTokenValidity: Duration.hours(1),
      refreshTokenValidity: Duration.days(1),
      oAuth: {
        flows: { authorizationCodeGrant: true },
        callbackUrls,
        logoutUrls: callbackUrls,
        scopes: [
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.resourceServer(resourceServer, reviewScope),
        ],
      },
    });
    const authDomainPrefix =
      config.authDomainPrefix ?? `clearpath-${Aws.ACCOUNT_ID}`;
    const authDomain = userPool.addDomain("ManagedLogin", {
      cognitoDomain: { domainPrefix: authDomainPrefix },
      managedLoginVersion: cognito.ManagedLoginVersion.CLASSIC_HOSTED_UI,
    });

    const bucket = config.existingBucketName
      ? s3.Bucket.fromBucketName(this, "Documents", config.existingBucketName)
      : new s3.Bucket(this, "Documents", {
          blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
          encryption: s3.BucketEncryption.S3_MANAGED,
          objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
          enforceSSL: true,
          removalPolicy: RemovalPolicy.RETAIN,
          autoDeleteObjects: false,
          cors: frontendOrigins.length
            ? [
                {
                  allowedOrigins: frontendOrigins,
                  allowedMethods: [s3.HttpMethods.POST],
                  allowedHeaders: ["*"],
                  exposedHeaders: ["ETag"],
                  maxAge: 300,
                },
              ]
            : undefined,
        });
    const table = config.existingTableName
      ? dynamodb.Table.fromTableName(this, "Cases", config.existingTableName)
      : new dynamodb.Table(this, "Cases", {
          partitionKey: { name: "id", type: dynamodb.AttributeType.STRING },
          billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
          encryption: dynamodb.TableEncryption.AWS_MANAGED,
          pointInTimeRecoverySpecification: {
            pointInTimeRecoveryEnabled: true,
          },
          deletionProtection: true,
          removalPolicy: RemovalPolicy.RETAIN,
        });

    let guardrailId = config.guardrailId;
    let guardrailVersion = config.guardrailVersion;
    if (!guardrailId) {
      const guardrail = new bedrock.CfnGuardrail(this, "PrivacyGuardrail", {
        name: `${this.stackName}-privacy`,
        description:
          "Defense in depth for synthetic ClearPath data; not a compliance guarantee.",
        blockedInputMessaging: "Input withheld for privacy review.",
        blockedOutputsMessaging: "Output withheld for privacy review.",
        sensitiveInformationPolicyConfig: {
          piiEntitiesConfig: [
            "NAME",
            "ADDRESS",
            "EMAIL",
            "PHONE",
            "US_SOCIAL_SECURITY_NUMBER",
            "US_BANK_ACCOUNT_NUMBER",
            "CREDIT_DEBIT_CARD_NUMBER",
            "US_PASSPORT_NUMBER",
            "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER",
            "USERNAME",
            "PASSWORD",
          ].map((type) => ({ type, action: "ANONYMIZE" })),
          regexesConfig: [
            {
              name: "LabeledFinancialIdentifier",
              description:
                "Mask labeled account/customer identifiers in addition to built-in PII detection.",
              pattern:
                "(?i)(?:account|acct|client|customer)[ \\t]*(?:number|no\\.?|id|#)[ \\t]*[:=]?[ \\t]*[A-Z0-9][A-Z0-9-]{3,31}",
              action: "ANONYMIZE",
            },
          ],
        },
        contentPolicyConfig: {
          filtersConfig: [
            "SEXUAL",
            "VIOLENCE",
            "HATE",
            "INSULTS",
            "MISCONDUCT",
          ].map((type) => ({
            type,
            inputStrength: "HIGH",
            outputStrength: "HIGH",
          })),
        },
      });
      guardrail.applyRemovalPolicy(RemovalPolicy.RETAIN);
      const version = new bedrock.CfnGuardrailVersion(
        this,
        "PrivacyGuardrailVersion",
        {
          guardrailIdentifier: guardrail.attrGuardrailId,
          description: "Published ClearPath privacy configuration.",
        },
      );
      version.applyRemovalPolicy(RemovalPolicy.RETAIN);
      guardrailId = guardrail.attrGuardrailId;
      guardrailVersion = version.attrVersion;
    }
    const guardrailArn = guardrailId!.startsWith("arn:")
      ? guardrailId!
      : this.formatArn({
          service: "bedrock",
          resource: "guardrail",
          resourceName: guardrailId,
          arnFormat: ArnFormat.SLASH_RESOURCE_NAME,
        });
    if (config.modelId.includes("*"))
      throw new Error("modelId cannot contain wildcards.");
    // Short IDs designate foundation models. Inference profiles must be supplied
    // as their full ARN plus the exact destination foundation-model ARNs.
    const modelArn = config.modelId.startsWith("arn:")
      ? config.modelId
      : this.formatArn({
          service: "bedrock",
          account: "",
          resource: "foundation-model",
          resourceName: config.modelId,
          arnFormat: ArnFormat.SLASH_RESOURCE_NAME,
        });

    const backendRoot = path.resolve(__dirname, "../../../backend");
    const infraRoot = path.resolve(__dirname, "../..");
    const code =
      props.backendCode ??
      lambda.Code.fromAsset(backendRoot, {
        exclude: [
          ".venv",
          "__pycache__",
          "*.pyc",
          ".pytest_cache",
          "tests",
          ".env",
          ".env.*",
        ],
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          platform: "linux/amd64",
          volumes: [{ hostPath: infraRoot, containerPath: "/clearpath-infra" }],
          command: [
            "python",
            "/clearpath-infra/bundle_backend.py",
            "/asset-input",
            "/asset-output",
          ],
          local: config.localBundling
            ? {
                tryBundle(outputDir: string): boolean {
                  const result = spawnSync(
                    "python3",
                    [
                      path.join(infraRoot, "bundle_backend.py"),
                      backendRoot,
                      outputDir,
                    ],
                    {
                      stdio: "inherit",
                    },
                  );
                  if (result.error || result.status !== 0)
                    throw new Error("Local backend packaging failed.");
                  return true;
                },
              }
            : undefined,
        },
      });
    const environment: Record<string, string> = {
      APP_MODE: "aws",
      S3_DOCUMENT_BUCKET: bucket.bucketName,
      DYNAMODB_CASES_TABLE: table.tableName,
      BEDROCK_MODEL_ID: config.modelId,
      BEDROCK_GUARDRAIL_ID: guardrailId!,
      BEDROCK_GUARDRAIL_VERSION: guardrailVersion!,
      CORS_ALLOWED_ORIGINS: frontendOrigins.join(","),
    };
    // AWS_REGION is provided by Lambda. AWS_PROFILE must never be set here:
    // deployed functions use their execution roles, not workstation profiles.
    const workerLog = new logs.LogGroup(this, "WorkerLogs", {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const apiLog = new logs.LogGroup(this, "ApiLogs", {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const workerRole = new iam.Role(this, "WorkerRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    });
    const apiRole = new iam.Role(this, "ApiRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    });
    workerLog.grantWrite(workerRole);
    apiLog.grantWrite(apiRole);
    const memory = new ClearPathMemory(this, "AgentCoreMemory", {
      existingMemoryId: config.existingMemoryId,
      enableSemanticMemory: config.enableSemanticMemory,
      memoryProcessingRegionConfirmed: config.memoryProcessingRegionConfirmed,
      eventExpiryDays: config.memoryEventExpiryDays,
      permissionsBoundary,
    });

    const failedJobs = new sqs.Queue(this, "FailedJobs", {
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      enforceSSL: true,
      retentionPeriod: Duration.days(14),
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const worker = new lambda.Function(this, "Worker", {
      functionName: config.workerFunctionName,
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.X86_64,
      handler: "app.handlers.worker.handler",
      code,
      role: workerRole,
      logGroup: workerLog,
      memorySize: 1024,
      timeout: Duration.minutes(5),
      environment,
      retryAttempts: 2,
      maxEventAge: Duration.hours(1),
      onFailure: new destinations.SqsDestination(failedJobs),
    });
    const api = new lambda.Function(this, "Api", {
      functionName: config.apiFunctionName,
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.X86_64,
      handler: "app.handlers.api.handler",
      code,
      role: apiRole,
      logGroup: apiLog,
      memorySize: 512,
      timeout: Duration.seconds(28),
      environment: {
        ...environment,
        WORKER_LAMBDA_FUNCTION_NAME: worker.functionName,
      },
    });
    for (const role of [apiRole, workerRole]) {
      role.addToPolicy(
        new iam.PolicyStatement({
          actions: ["dynamodb:GetItem", "dynamodb:PutItem"],
          resources: [table.tableArn],
        }),
      );
    }
    apiRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:GetObject", "s3:PutObject"],
        resources: [bucket.arnForObjects("*")],
      }),
    );
    workerRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:GetObject"],
        resources: [bucket.arnForObjects("*")],
      }),
    );
    workerRole.addToPolicy(
      new iam.PolicyStatement({
        // DetectDocumentText does not support resource-level IAM permissions.
        actions: ["textract:DetectDocumentText"],
        resources: ["*"],
      }),
    );
    workerRole.addToPolicy(
      new iam.PolicyStatement({
        // Converse is authorized by InvokeModel, not a bedrock:Converse IAM action.
        actions: ["bedrock:InvokeModel"],
        resources: [modelArn, ...config.additionalModelArns],
      }),
    );
    workerRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:ApplyGuardrail"],
        resources: [guardrailArn],
      }),
    );
    worker.grantInvoke(apiRole);

    const jwtAuthorizer = new authorizers.HttpJwtAuthorizer(
      "CognitoAuthorizer",
      `https://cognito-idp.${this.region}.${this.urlSuffix}/${userPool.userPoolId}`,
      { jwtAudience: [userPoolClient.userPoolClientId] },
    );
    const httpApi = new apigw.HttpApi(this, "HttpApi", {
      apiName: `${this.stackName}-http`,
      defaultIntegration: new integrations.HttpLambdaIntegration(
        "ApiIntegration",
        api,
      ),
      defaultAuthorizer: jwtAuthorizer,
      defaultAuthorizationScopes: ["clearpath/review"],
      corsPreflight: frontendOrigins.length
        ? {
            allowOrigins: frontendOrigins,
            allowMethods: [
              apigw.CorsHttpMethod.GET,
              apigw.CorsHttpMethod.POST,
              apigw.CorsHttpMethod.PUT,
              apigw.CorsHttpMethod.OPTIONS,
            ],
            allowHeaders: [
              "Content-Type",
              "Authorization",
              "X-Amz-Date",
              "X-Amz-Security-Token",
              "X-Amz-Content-Sha256",
            ],
            maxAge: Duration.minutes(5),
          }
        : undefined,
    });
    const stage = httpApi.defaultStage!.node.defaultChild as apigw.CfnStage;
    stage.defaultRouteSettings = {
      throttlingBurstLimit: 20,
      throttlingRateLimit: 10,
    };

    new CfnOutput(this, "ApiUrl", { value: httpApi.apiEndpoint });
    new CfnOutput(this, "DocumentBucketName", { value: bucket.bucketName });
    new CfnOutput(this, "CasesTableName", { value: table.tableName });
    new CfnOutput(this, "WorkerFunctionName", { value: worker.functionName });
    new CfnOutput(this, "GuardrailId", { value: guardrailId! });
    new CfnOutput(this, "GuardrailVersion", { value: guardrailVersion! });
    new CfnOutput(this, "FailedJobsQueueUrl", { value: failedJobs.queueUrl });
    new CfnOutput(this, "UserPoolId", { value: userPool.userPoolId });
    new CfnOutput(this, "UserPoolClientId", {
      value: userPoolClient.userPoolClientId,
    });
    new CfnOutput(this, "AuthDomain", { value: authDomain.baseUrl() });
    new CfnOutput(this, "AuthScope", { value: "clearpath/review" });
    new CfnOutput(this, "AgentCoreMemoryId", { value: memory.memoryId });
    new CfnOutput(this, "AgentCoreMemoryArn", { value: memory.memoryArn });
  }
}
