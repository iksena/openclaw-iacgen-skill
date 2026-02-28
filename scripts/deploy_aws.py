#!/usr/bin/env python3
"""Gate 3: Live AWS CloudFormation deployment validation for IaCGen OpenClaw Skill.

Creates a real CloudFormation stack, polls for completion, then immediately
deletes it. This mirrors IaCGen's original live-deployment evaluation gate.

Usage:
    python3 deploy_aws.py <template_path>

Required environment variables:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION   (defaults to us-east-1 if not set)

Exits 0 on success, 1 on failure.
Prints JSON result to stdout. Progress lines go to stderr.
"""
import sys
import json
import time
import uuid
import os

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print(json.dumps({
        "success": False,
        "failed_reason": "boto3 not installed. Run: pip install boto3"
    }))
    sys.exit(1)

POLL_INTERVAL_SECONDS = 3
MAX_WAIT_SECONDS = 300  # 5-minute hard cap

TERMINAL_STATUSES = {
    "CREATE_COMPLETE",
    "CREATE_FAILED",
    "ROLLBACK_COMPLETE",
    "ROLLBACK_FAILED",
    "DELETE_COMPLETE",
}


def deploy_template(template_path: str) -> dict:
    # Credential check
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        return {"success": False, "failed_reason": "AWS_ACCESS_KEY_ID not set"}
    if not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return {"success": False, "failed_reason": "AWS_SECRET_ACCESS_KEY not set"}

    try:
      with open(template_path, "r") as f:
            template_body = f.read()
    except FileNotFoundError:
        return {"success": False, "failed_reason": f"File not found: {template_path}"}

    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    stack_name = f"iacgen-val-{uuid.uuid4().hex[:8]}"
    cfn = boto3.client("cloudformation", region_name=region)

    print(f"[deploy] Creating stack '{stack_name}' in {region}...", file=sys.stderr)

    try:
        cfn.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            OnFailure="DELETE",
            Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg  = e.response["Error"]["Message"]
        return {"success": False, "failed_reason": f"{error_code}: {error_msg}"}

    # --- Polling loop ---
    completed_resources = []
    failed_reasons = []
    deadline = time.time() + MAX_WAIT_SECONDS

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)

        try:
            resp = cfn.describe_stacks(StackName=stack_name)
        except ClientError:
            break  # Stack deleted itself (OnFailure=DELETE)

        stacks = resp.get("Stacks", [])
        if not stacks:
            break

        stack  = stacks[0]
        status = stack["StackStatus"]
        print(f"[deploy]   status: {status}", file=sys.stderr)

        if status in TERMINAL_STATUSES:
            # Harvest per-resource events
            try:
                paginator = cfn.get_paginator("describe_stack_events")
                for page in paginator.paginate(StackName=stack_name):
                    for event in page["StackEvents"]:
                        res_id     = event.get("LogicalResourceId", "")
                        res_status = event.get("ResourceStatus", "")
                        reason     = event.get("ResourceStatusReason", "")

                        if res_status == "CREATE_COMPLETE" and res_id != stack_name:
                            completed_resources.append(res_id)
                        if res_status == "CREATE_FAILED" and res_id != stack_name and reason:
                            failed_reasons.append(f"Resource {res_id}: {reason}")
                            print(f"[deploy]   FAILED — {res_id}: {reason}", file=sys.stderr)
            except ClientError:
                pass

            # Cleanup
            if status not in ("DELETE_COMPLETE",):
                try:
                    cfn.delete_stack(StackName=stack_name)
                    print("[deploy] Cleanup: deleting stack...", file=sys.stderr)
                except ClientError:
                    pass

            return {
                "success": status == "CREATE_COMPLETE",
                "stack_name": stack_name,
                "stack_status": status,
                "region": region,
                "failed_reason": failed_reasons[0] if failed_reasons else "",
                "all_failed_reasons": failed_reasons,
                "completed_resources": list(set(completed_resources)),
            }

    # Timeout reached — clean up
    try:
        cfn.delete_stack(StackName=stack_name)
    except ClientError:
        pass

    return {
        "success": False,
        "stack_name": stack_name,
        "failed_reason": f"Timed out after {MAX_WAIT_SECONDS}s waiting for stack to reach terminal status",
        "completed_resources": list(set(completed_resources)),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "failed_reason": "Usage: deploy_aws.py <template_path>"
        }))
        sys.exit(1)

    result = deploy_template(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
