"""Deploy the beta stack, migrate once, then start and smoke-test the service.

Uses the current AWS session locally or GitHub OIDC in CI. Never seeds accounts.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REGION = "ap-southeast-2"


def run(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout


def aws(*args):
    return json.loads(run("aws", *args, "--region", REGION, "--output", "json") or "{}")


def main():
    # Fail before creating resources if the organization blocks the required region.
    aws("sts", "get-caller-identity")
    aws("cloudformation", "describe-stacks", "--stack-name", "CDKToolkit")
    with tempfile.TemporaryDirectory(prefix="stitchcore-deploy-") as work:
        outputs_path = Path(work) / "outputs.json"
        assembly = Path(work) / "assembly"
        base = ("npx", "--no-install", "cdk")
        cdk_dir = ROOT / "infra/cdk"
        # initialize=true is exclusively for first-time creation; it would otherwise
        # stop an existing service. The operator chooses it explicitly.
        initialize = "--initialize" in sys.argv[1:]
        if set(sys.argv[1:]) - {"--initialize"}:
            raise SystemExit("Usage: python scripts/deploy_beta.py [--initialize]")
        args = ["deploy", "StitchCore-beta", "-c", "env=beta", "--outputs-file", str(outputs_path),
                "--output", str(assembly), "--require-approval", "never"]
        if initialize:
            args += ["-c", "initialize=true"]
        print("Deploying beta infrastructure and immutable container assets.", flush=True)
        subprocess.run((*base, *args), cwd=cdk_dir, check=True)
        outputs = json.loads(outputs_path.read_text())["StitchCore-beta"]
        network = {"awsvpcConfiguration": {
            "subnets": outputs["PublicSubnetIds"].split(","),
            "securityGroups": [outputs["MigrationSecurityGroupId"]],
            "assignPublicIp": "ENABLED",
        }}
        result = aws("ecs", "run-task", "--cluster", outputs["ClusterName"],
                     "--task-definition", outputs["MigrationTaskArn"], "--launch-type", "FARGATE",
                     "--network-configuration", json.dumps(network))
        if result.get("failures") or not result.get("tasks"):
            raise RuntimeError("Could not launch the migration task; inspect ECS task failures.")
        task_arn = result["tasks"][0]["taskArn"]
        subprocess.run(("aws", "ecs", "wait", "tasks-stopped", "--cluster", outputs["ClusterName"],
                        "--tasks", task_arn, "--region", REGION), check=True)
        task = aws("ecs", "describe-tasks", "--cluster", outputs["ClusterName"], "--tasks", task_arn)["tasks"][0]
        containers = task.get("containers", [])
        if not containers or any(c.get("exitCode") != 0 for c in containers):
            raise RuntimeError("Migration failed; inspect the migration CloudWatch logs. Service not started.")
        if initialize:
            print("Migrations succeeded. Starting beta web/API service.", flush=True)
            subprocess.run((*base, "deploy", "StitchCore-beta", "-c", "env=beta",
                            "--output", str(assembly), "--require-approval", "never"),
                           cwd=cdk_dir, check=True)
        subprocess.run(("aws", "ecs", "wait", "services-stable", "--cluster", outputs["ClusterName"],
                        "--services", outputs["ServiceName"], "--region", REGION), check=True)
        website = outputs["WebsiteUrl"]
        for suffix in ("/", "/health/", "/api/v1/catalog/services"):
            with urllib.request.urlopen(website + suffix, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"Smoke test failed for {suffix}.")
        print(f"Beta website verified: {website}")
        print("OTP, payment, and notification providers require separate configuration.")


if __name__ == "__main__":
    main()
