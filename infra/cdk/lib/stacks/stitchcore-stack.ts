import * as path from "path";
import { Duration, RemovalPolicy, Stack, StackProps, CfnOutput } from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecsPatterns from "aws-cdk-lib/aws-ecs-patterns";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as lambdaEvents from "aws-cdk-lib/aws-lambda-event-sources";
import * as logs from "aws-cdk-lib/aws-logs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sqs from "aws-cdk-lib/aws-sqs";
import { Construct } from "constructs";
import { EnvironmentConfig } from "../config/environment";

export class StitchCoreStack extends Stack {
  constructor(scope: Construct, id: string, config: EnvironmentConfig, props?: StackProps) {
    super(scope, id, { ...props, env: { account: config.account || undefined, region: config.region } });
    const retain = config.deletionProtection ? RemovalPolicy.RETAIN : RemovalPolicy.DESTROY;
    const vpc = new ec2.Vpc(this, "Vpc", { maxAzs: 2, natGateways: 0, subnetConfiguration: [{ name: "public", subnetType: ec2.SubnetType.PUBLIC }, { name: "isolated", subnetType: ec2.SubnetType.PRIVATE_ISOLATED }] });
    const mediaBucket = new s3.Bucket(this, "MediaBucket", { encryption: s3.BucketEncryption.S3_MANAGED, blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL, enforceSSL: true, removalPolicy: retain, autoDeleteObjects: !config.deletionProtection, lifecycleRules: [{ expiration: Duration.days(365) }] });
    const dlq = new sqs.Queue(this, "NotificationDlq", { retentionPeriod: Duration.days(14), removalPolicy: retain });
    const notificationQueue = new sqs.Queue(this, "NotificationQueue", { visibilityTimeout: Duration.seconds(60), deadLetterQueue: { queue: dlq, maxReceiveCount: 3 }, removalPolicy: retain });
    const dbSecurityGroup = new ec2.SecurityGroup(this, "DatabaseSecurityGroup", { vpc, allowAllOutbound: false });
    const database = new rds.DatabaseInstance(this, "Database", { engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_16 }), vpc, vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED }, securityGroups: [dbSecurityGroup], credentials: rds.Credentials.fromGeneratedSecret("stitchcore"), allocatedStorage: 20, maxAllocatedStorage: 100, backupRetention: Duration.days(config.backupRetentionDays), deletionProtection: config.deletionProtection, removalPolicy: retain, publiclyAccessible: false, multiAz: config.deletionProtection });
    const cluster = new ecs.Cluster(this, "Cluster", { vpc });
    const repository = new ecr.Repository(this, "BackendRepository", { imageScanOnPush: true, removalPolicy: retain, emptyOnDelete: !config.deletionProtection });
    const logGroup = new logs.LogGroup(this, "ApiLogs", { retention: config.logRetentionDays as logs.RetentionDays, removalPolicy: retain });
    const service = new ecsPatterns.ApplicationLoadBalancedFargateService(this, "Api", { cluster, desiredCount: config.apiDesiredCount, cpu: config.apiCpu, memoryLimitMiB: config.apiMemoryMiB, publicLoadBalancer: true, assignPublicIp: true, taskImageOptions: { image: ecs.ContainerImage.fromEcrRepository(repository, "latest"), containerPort: 8000, environment: { DEBUG: "false", DB_ENGINE: "django.db.backends.postgresql", DB_HOST: database.dbInstanceEndpointAddress, DB_PORT: database.dbInstanceEndpointPort, DB_NAME: "stitchcore", AWS_REGION: config.region, AWS_S3_MEDIA_BUCKET: mediaBucket.bucketName, AWS_SQS_NOTIFICATION_QUEUE_URL: notificationQueue.queueUrl }, secrets: { DJANGO_SECRET_KEY: ecs.Secret.fromSecretsManager(database.secret!, "password"), DB_USER: ecs.Secret.fromSecretsManager(database.secret!, "username"), DB_PASSWORD: ecs.Secret.fromSecretsManager(database.secret!, "password") }, logDriver: ecs.LogDrivers.awsLogs({ streamPrefix: "api", logGroup }) } });
    database.connections.allowDefaultPortFrom(service.service, "API to PostgreSQL");
    mediaBucket.grantReadWrite(service.taskDefinition.taskRole);
    notificationQueue.grantSendMessages(service.taskDefinition.taskRole);
    database.secret?.grantRead(service.taskDefinition.executionRole!);
    service.targetGroup.configureHealthCheck({ path: "/api/docs/", healthyHttpCodes: "200,301,302" });
    const notificationFn = new lambda.Function(this, "NotificationFunction", { runtime: lambda.Runtime.PYTHON_3_12, handler: "handler.handler", code: lambda.Code.fromAsset(path.join(__dirname, "../../../../infra/lambda/notifications")), timeout: Duration.seconds(30), environment: { INTERNAL_API_BASE_URL: `http://${service.loadBalancer.loadBalancerDnsName}`, INTERNAL_NOTIFICATION_SECRET: "configure-in-secrets-manager" } });
    notificationFn.addEventSource(new lambdaEvents.SqsEventSource(notificationQueue, { batchSize: 10, reportBatchItemFailures: true }));
    notificationQueue.grantConsumeMessages(notificationFn);
    notificationFn.addToRolePolicy(new iam.PolicyStatement({ actions: ["secretsmanager:GetSecretValue"], resources: ["*"] }));
    new CfnOutput(this, "ApiUrl", { value: `http://${service.loadBalancer.loadBalancerDnsName}` });
    new CfnOutput(this, "MediaBucketName", { value: mediaBucket.bucketName });
    new CfnOutput(this, "NotificationQueueUrl", { value: notificationQueue.queueUrl });
  }
}

