#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { environmentConfig } from "../lib/config/environment";
import { StitchCoreStack } from "../lib/stacks/stitchcore-stack";
const app = new cdk.App(); const config = environmentConfig(app.node.tryGetContext("env") ?? "beta", app.node.tryGetContext("initialize") === "true"); new StitchCoreStack(app, `StitchCore-${config.name}`, config, { description: `StitchCore ${config.name} environment` });

