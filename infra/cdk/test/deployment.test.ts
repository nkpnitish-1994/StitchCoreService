import * as assert from "node:assert/strict";
import { App } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { StitchCoreStack } from "../lib/stacks/stitchcore-stack";
import { environmentConfig } from "../lib/config/environment";

for (const name of ["beta", "production"]) {
  const app = new App({ outdir: `/tmp/stitchcore-test-${name}` });
  const config = environmentConfig(name);
  assert.equal(config.region, "ap-southeast-2");
  const stack = new StitchCoreStack(app, `Test-${name}`, config);
  const template = Template.fromStack(stack);
  template.resourceCountIs("AWS::EC2::NatGateway", 0);
  template.hasResourceProperties("AWS::RDS::DBInstance", {
    DBName: "stitchcore", PubliclyAccessible: false, StorageEncrypted: true,
    DeletionProtection: name === "production",
  });
  template.hasResourceProperties("AWS::ECS::Service", {
    DesiredCount: config.apiDesiredCount,
    DeploymentConfiguration: Match.objectLike({ DeploymentCircuitBreaker: { Enable: true, Rollback: true } }),
  });
  template.hasResourceProperties("AWS::ECS::TaskDefinition", {
    ContainerDefinitions: Match.arrayWith([
      Match.objectLike({ Name: "api", PortMappings: [{ ContainerPort: 8000, Protocol: "tcp" }] }),
      Match.objectLike({ Name: "web", PortMappings: [{ ContainerPort: 3000, Protocol: "tcp" }] }),
    ]),
  });
  template.hasResourceProperties("AWS::ElasticLoadBalancingV2::Listener", {
    DefaultActions: [{ FixedResponseConfig: { StatusCode: "403" }, Type: "fixed-response" }],
  });
  template.hasResourceProperties("AWS::CloudFront::Distribution", {
    DistributionConfig: Match.objectLike({
      DefaultCacheBehavior: Match.objectLike({ ViewerProtocolPolicy: "redirect-to-https" }),
    }),
  });
  template.hasResourceProperties("AWS::SQS::Queue", { RedrivePolicy: Match.objectLike({ maxReceiveCount: 3 }) });
  template.resourceCountIs("AWS::Lambda::EventSourceMapping", 0);
  template.hasResourceProperties("AWS::ECS::TaskDefinition", {
    ContainerDefinitions: Match.arrayWith([Match.objectLike({
      Name: "migration", Command: ["python", "manage.py", name === "beta" ? "prepare_beta" : "migrate_locked"],
    })]),
  });
}
assert.equal(environmentConfig("beta", true).apiDesiredCount, 0);
assert.throws(() => environmentConfig("unknown"));
console.log("Deployment assertions passed for beta and production.");
