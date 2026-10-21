import * as path from "path";
import { Duration, RemovalPolicy, Stack, StackProps, CfnOutput, Tags } from "aws-cdk-lib";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as sqs from "aws-cdk-lib/aws-sqs";
import { Construct } from "constructs";
import { EnvironmentConfig } from "../config/environment";

export class StitchCoreStack extends Stack {
  constructor(scope: Construct, id: string, config: EnvironmentConfig, props?: StackProps) {
    super(scope, id, { ...props, env: { account: config.account || undefined, region: config.region } });
    const retain = config.deletionProtection ? RemovalPolicy.RETAIN : RemovalPolicy.SNAPSHOT;
    Tags.of(this).add("Project", "StitchCore");
    Tags.of(this).add("Environment", config.name);
    Tags.of(this).add("Owner", "StitchCore");
    Tags.of(this).add("CostCenter", "StitchCore");
    const vpc = new ec2.Vpc(this, "Vpc", {
      maxAzs: 2, natGateways: 0,
      subnetConfiguration: [
        { name: "public", subnetType: ec2.SubnetType.PUBLIC },
        { name: "isolated", subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      ],
    });
    const mediaBucket = new s3.Bucket(this, "MediaBucket", {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL, enforceSSL: true,
      removalPolicy: RemovalPolicy.RETAIN,
      lifecycleRules: [{ expiration: Duration.days(365) }],
    });
    const dlq = new sqs.Queue(this, "NotificationDlq", {
      retentionPeriod: Duration.days(14), encryption: sqs.QueueEncryption.SQS_MANAGED,
    });
    const queue = new sqs.Queue(this, "NotificationQueue", {
      visibilityTimeout: Duration.seconds(60), encryption: sqs.QueueEncryption.SQS_MANAGED,
      deadLetterQueue: { queue: dlq, maxReceiveCount: 3 },
    });
    const database = new rds.DatabaseInstance(this, "Database", {
      engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_16 }),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
      databaseName: "stitchcore",
      vpc, vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      credentials: rds.Credentials.fromGeneratedSecret("stitchcore"),
      allocatedStorage: 20, maxAllocatedStorage: 100, storageEncrypted: true,
      backupRetention: Duration.days(config.backupRetentionDays),
      deletionProtection: config.deletionProtection, removalPolicy: retain,
      publiclyAccessible: false, multiAz: config.deletionProtection,
    });
    const appSecret = new secretsmanager.Secret(this, "ApplicationSecret", {
      generateSecretString: { passwordLength: 64, excludePunctuation: true },
    });
    const internalSecret = new secretsmanager.Secret(this, "InternalNotificationSecret", {
      generateSecretString: { passwordLength: 64, excludePunctuation: true },
    });
    const originSecret = new secretsmanager.Secret(this, "OriginSecret", {
      generateSecretString: { passwordLength: 48, excludePunctuation: true },
    });
    const betaAdminSecret = config.name === "beta" ? new secretsmanager.Secret(this, "BetaAdminAccess", {
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: "beta-admin" }),
        generateStringKey: "password", passwordLength: 32, excludePunctuation: true,
      },
    }) : undefined;
    const betaCustomerSecret = config.name === "beta" ? new secretsmanager.Secret(this, "BetaCustomerAccess", {
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: "beta-customer" }),
        generateStringKey: "password", passwordLength: 32, excludePunctuation: true,
      },
    }) : undefined;
    const cluster = new ecs.Cluster(this, "Cluster", { vpc });
    const loadBalancer = new elbv2.ApplicationLoadBalancer(this, "LoadBalancer", {
      vpc, internetFacing: true,
    });
    const listener = loadBalancer.addListener("Http", {
      port: 80,
      defaultAction: elbv2.ListenerAction.fixedResponse(403),
    });
    const apiOrigin = new origins.LoadBalancerV2Origin(loadBalancer, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      customHeaders: { "X-StitchCore-Origin": originSecret.secretValue.unsafeUnwrap() },
    });
    const originPolicy = new cloudfront.OriginRequestPolicy(this, "OriginPolicy", {
      headerBehavior: cloudfront.OriginRequestHeaderBehavior.all("CloudFront-Forwarded-Proto"),
      cookieBehavior: cloudfront.OriginRequestCookieBehavior.all(),
      queryStringBehavior: cloudfront.OriginRequestQueryStringBehavior.all(),
    });
    const dynamicBehavior = {
      origin: apiOrigin,
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      originRequestPolicy: originPolicy,
      allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
      responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
    };
    const distribution = new cloudfront.Distribution(this, "Website", {
      defaultBehavior: dynamicBehavior,
      additionalBehaviors: { "api/*": dynamicBehavior, "admin/*": dynamicBehavior },
    });
    const apiImage = ecs.ContainerImage.fromAsset(path.join(__dirname, "../../../.."), {
      exclude: [".git", ".aws", ".codex", ".agents", ".venv", "**/node_modules", "**/.next", "**/cdk.out", "**/dist"],
    });
    const apiEnvironment = {
      DEBUG: "false", ALLOWED_HOSTS: "*",
      DB_ENGINE: "django.db.backends.postgresql",
      DB_HOST: database.dbInstanceEndpointAddress, DB_PORT: database.dbInstanceEndpointPort,
      DB_NAME: "stitchcore", AWS_REGION: config.region, STITCHCORE_ENV: config.name,
      AWS_S3_MEDIA_BUCKET: mediaBucket.bucketName, AWS_SQS_NOTIFICATION_QUEUE_URL: queue.queueUrl,
      OTP_PROVIDER: "disabled", BETA_AUTH_ENABLED: String(config.name === "beta"), CSRF_TRUSTED_ORIGINS: `https://${distribution.distributionDomainName}`,
    };
    const apiSecrets = {
      DJANGO_SECRET_KEY: ecs.Secret.fromSecretsManager(appSecret),
      INTERNAL_NOTIFICATION_SECRET: ecs.Secret.fromSecretsManager(internalSecret),
      DB_USER: ecs.Secret.fromSecretsManager(database.secret!, "username"),
      DB_PASSWORD: ecs.Secret.fromSecretsManager(database.secret!, "password"),
    };
    const task = new ecs.FargateTaskDefinition(this, "WebApiTask", {
      cpu: config.apiCpu, memoryLimitMiB: config.apiMemoryMiB,
    });
    const api = task.addContainer("api", {
      image: apiImage, environment: apiEnvironment, secrets: apiSecrets,
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "api", logRetention: config.logRetentionDays as logs.RetentionDays,
      }),
      portMappings: [{ containerPort: 8000 }],
    });
    const web = task.addContainer("web", {
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, "../../../../frontend/web")),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "web", logRetention: config.logRetentionDays as logs.RetentionDays,
      }),
      portMappings: [{ containerPort: 3000 }],
    });
    const service = new ecs.FargateService(this, "Service", {
      cluster, taskDefinition: task, desiredCount: config.apiDesiredCount,
      assignPublicIp: true, vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      circuitBreaker: { rollback: true }, healthCheckGracePeriod: Duration.seconds(90),
    });
    database.connections.allowDefaultPortFrom(service);
    const secretCondition = elbv2.ListenerCondition.httpHeader("X-StitchCore-Origin", [
      originSecret.secretValue.unsafeUnwrap(),
    ]);
    listener.addTargets("ApiTargets", {
      priority: 10,
      conditions: [secretCondition, elbv2.ListenerCondition.pathPatterns(["/api/*", "/admin", "/admin/*", "/static/*", "/health/"])],
      port: 8000, protocol: elbv2.ApplicationProtocol.HTTP, targets: [service.loadBalancerTarget({ containerName: api.containerName, containerPort: 8000 })],
      healthCheck: { path: "/health/", healthyHttpCodes: "200" },
      deregistrationDelay: Duration.seconds(15),
    });
    listener.addTargets("WebTargets", {
      priority: 20, conditions: [secretCondition],
      port: 3000, protocol: elbv2.ApplicationProtocol.HTTP, targets: [service.loadBalancerTarget({ containerName: web.containerName, containerPort: 3000 })],
      healthCheck: { path: "/", healthyHttpCodes: "200" },
      deregistrationDelay: Duration.seconds(15),
    });
    mediaBucket.grantReadWrite(task.taskRole);
    queue.grantSendMessages(task.taskRole);
    const migrationTask = new ecs.FargateTaskDefinition(this, "MigrationTask", {
      cpu: 512, memoryLimitMiB: 1024,
    });
    migrationTask.addContainer("migration", {
      image: apiImage, environment: apiEnvironment, secrets: {
        ...apiSecrets,
        ...(betaAdminSecret && betaCustomerSecret ? {
          BETA_ADMIN_PASSWORD: ecs.Secret.fromSecretsManager(betaAdminSecret, "password"),
          BETA_CUSTOMER_PASSWORD: ecs.Secret.fromSecretsManager(betaCustomerSecret, "password"),
        } : {}),
      },
      command: ["python", "manage.py", config.name === "beta" ? "prepare_beta" : "migrate_locked"],
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "migration", logRetention: config.logRetentionDays as logs.RetentionDays,
      }),
    });
    const migrationSecurityGroup = new ec2.SecurityGroup(this, "MigrationSecurityGroup", { vpc });
    database.connections.allowDefaultPortFrom(migrationSecurityGroup);
    // Keep the adapter packaged but disconnected until real providers are configured.
    // The current adapter must never falsely record a notification as sent.
    const notificationFn = new lambda.Function(this, "NotificationFunction", {
      runtime: lambda.Runtime.PYTHON_3_12, handler: "handler.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "../../../../infra/lambda/notifications")),
      timeout: Duration.seconds(30),
      environment: {
        INTERNAL_API_BASE_URL: `https://${distribution.distributionDomainName}`,
        INTERNAL_NOTIFICATION_SECRET_ARN: internalSecret.secretArn,
      },
    });
    queue.grantConsumeMessages(notificationFn);
    internalSecret.grantRead(notificationFn);
    if (betaAdminSecret && betaCustomerSecret) {
      new CfnOutput(this, "BetaAdminSecretArn", { value: betaAdminSecret.secretArn });
      new CfnOutput(this, "BetaCustomerSecretArn", { value: betaCustomerSecret.secretArn });
    }
    new CfnOutput(this, "WebsiteUrl", { value: `https://${distribution.distributionDomainName}` });
    new CfnOutput(this, "ClusterName", { value: cluster.clusterName });
    new CfnOutput(this, "ServiceName", { value: service.serviceName });
    new CfnOutput(this, "MigrationTaskArn", { value: migrationTask.taskDefinitionArn });
    new CfnOutput(this, "MigrationSecurityGroupId", { value: migrationSecurityGroup.securityGroupId });
    new CfnOutput(this, "PublicSubnetIds", { value: vpc.publicSubnets.map(s => s.subnetId).join(",") });
    new CfnOutput(this, "MediaBucketName", { value: mediaBucket.bucketName });
    new CfnOutput(this, "NotificationQueueUrl", { value: queue.queueUrl });
  }
}
