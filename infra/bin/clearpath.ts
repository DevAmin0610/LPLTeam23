#!/usr/bin/env node
import { App } from "aws-cdk-lib";
import { ClearPathStack, readConfig } from "../lib/clearpath-stack";

const app = new App();
const region =
  app.node.tryGetContext("region") ?? process.env.CDK_DEFAULT_REGION;
const account =
  app.node.tryGetContext("account") ?? process.env.CDK_DEFAULT_ACCOUNT;
if (
  region !== undefined &&
  (typeof region !== "string" || !/^[a-z]{2}(?:-[a-z]+)+-\d+$/.test(region))
) {
  throw new Error("Invalid region context.");
}
if (
  account !== undefined &&
  (typeof account !== "string" || !/^\d{12}$/.test(account))
) {
  throw new Error("Invalid account context.");
}
new ClearPathStack(app, "ClearPath", {
  config: readConfig(app),
  // No fromLookup calls or implicit account discovery. Omitted values remain
  // environment-agnostic CloudFormation tokens until an approved deployment.
  env: region || account ? { region, account } : undefined,
});
app.synth();
