---
name: "iacgen"
description: "Generate deployable AWS CloudFormation YAML templates from a natural language business need. Uses IaCGen's iterative feedback loop — yamllint → cfn-lint → live AWS deployment — to reach a validated, deployable template. Activate when the user wants to generate, create, build, or write a CloudFormation template or AWS infrastructure-as-code (IaC)."
metadata: {"openclaw": {"emoji": "☁️", "requires": {"bins": ["python3", "cfn-lint"]}, "install": [{"id": "cfn-lint", "kind": "uv", "package": "cfn-lint"}, {"id": "yamllint", "kind": "uv", "package": "yamllint"}, {"id": "boto3", "kind": "uv", "package": "boto3"}]}}
---

# IaCGen — Deployability-Centric AWS CloudFormation Generator

This skill replicates the IaCGen framework (Zhang et al., FSE 2025). You are the LLM
generator. The three scripts in `{baseDir}/scripts/` are your validation gates. Your job
is to generate a CloudFormation template, validate it through all gates, and refine it
iteratively based on structured feedback until it passes.

## When to Activate
- User asks to generate, create, write, or build a CloudFormation / IaC template
- User describes AWS infrastructure in natural language and wants a YAML output
- User says "deploy X to AWS" and needs a template
- User mentions CloudFormation, AWS IaC, YAML template

---

## Iteration State (track these variables internally)

```
iteration        = 0   # total LLM call count
yaml_attempts    = 0   # failures at Gate 1
cfn_attempts     = 0   # failures at Gate 2
deploy_attempts  = 0   # failures at Gate 3
highest_feedback = "simple"   # escalates: simple → moderate → advanced
template_path    = "/tmp/iacgen_<unix_timestamp>_iter_1.yaml"
```

Max per gate: 10 attempts. If any gate counter hits 10, stop and report failure.

---

## Step-by-Step Execution

### STEP 1 — Parse the Business Need
Extract the infrastructure requirement from the user's message. If the request is
ambiguous about a critical design choice (e.g., public vs private bucket), ask ONE
clarifying question before proceeding.

### STEP 2 — Plan the Template
Before writing YAML, silently reason through:
1. Which AWS resource types are needed (e.g., `AWS::S3::Bucket`, `AWS::Lambda::Function`)
2. Resource dependency ordering (resources referenced by others come first, or use `!Ref`)
3. Required properties for each resource type (cfn-lint will catch missing required props)
4. Which resources need IAM roles or policies
5. DeletionPolicy / UpdateReplacePolicy needs
6. Useful Outputs (URLs, ARNs, stack exports)

### STEP 3 — Generate the Template
Write the complete CloudFormation YAML. Follow these rules strictly:

1. Start with `AWSTemplateFormatVersion: '2010-09-09'`
2. Include a `Description:` field
3. `DeletionPolicy` and `UpdateReplacePolicy` are **resource-level attributes** — place
   at the same indentation level as `Type:` and `Properties:`, **NOT inside `Properties:`**
4. Use `!Ref`, `!GetAtt`, `!Sub`, `!Join`, `!Select` for cross-resource references
5. No markdown fences, no backticks, no explanatory prose — pure YAML only
6. End with the last property of the last resource (or the Outputs section if present)

### STEP 4 — Save the Template
Write the YAML content to: `/tmp/iacgen_<unix_timestamp>_iter_<N>.yaml`

Use the write file tool. The file must contain raw YAML only.

### STEP 5 — Gate 1: YAML Format Validation
```bash
python3 {baseDir}/scripts/validate_yaml.py /tmp/iacgen_<timestamp>_iter_<N>.yaml
```

Read the JSON output:
- `{"passed": true}` → proceed to Gate 2
- `{"passed": false, "details": [...]}` → apply feedback, goto Step 3

**Feedback logic for Gate 1:**
- `yaml_attempts` 0–1: Fix the specific YAML structural error (indentation, duplicate key)
- `yaml_attempts` 2–5: Show explicit corrected YAML for the failing lines
- `yaml_attempts` 6–9: Rewrite the entire affected section from scratch
- `yaml_attempts >= 10`: Stop, report `max_attempts_exceeded` at `yaml_validation` gate

`yaml_attempts += 1` after each failure.

### STEP 6 — Gate 2: CloudFormation Syntax Validation
```bash
python3 {baseDir}/scripts/validate_cfn.py /tmp/iacgen_<timestamp>_iter_<N>.yaml
```

Read the JSON output:
- `{"passed": true}` → proceed to Gate 3 (or finish if deployment is skipped)
- `{"passed": false, "error_details": [...]}` → apply feedback, goto Step 3

**Feedback logic for Gate 2:**
- `cfn_attempts` 0–1: Note cfn-lint errors; fix them
- `cfn_attempts` 2–5: Address **every** error in `error_details` explicitly before rewriting
- `cfn_attempts` 6–9: Consult the `documentation` URL in each error for exact constraints
- `cfn_attempts >= 10`: Stop, report `max_attempts_exceeded` at `syntax_validation` gate

`cfn_attempts += 1` after each failure.

### STEP 7 — Gate 3: Live AWS Deployment *(optional)*
Skip Gate 3 if:
- User says "no deployment", "dry run", or "skip deployment"
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` are not set

Otherwise:
```bash
python3 {baseDir}/scripts/deploy_aws.py /tmp/iacgen_<timestamp>_iter_<N>.yaml
```

Read the JSON output:
- `{"success": true}` → done! Report success with stack details.
- `{"success": false, "failed_reason": "..."}` → apply feedback, goto Step 3

**Feedback logic for Gate 3:**
- `deploy_attempts` 0–1: Note the deployment failed; fix the conflicting AWS configuration
- `deploy_attempts` 2–5: Address the exact `failed_reason` text explicitly
  (e.g., `"Policy has been blocked by BlockPublicPolicy"` → set all 4
  `PublicAccessBlockConfiguration` fields to `false`)
- `deploy_attempts` 6–9: Reason through the full AWS service constraint causing the error
- `deploy_attempts >= 10`: Stop, report `max_attempts_exceeded` at `deployment` gate

`deploy_attempts += 1` after each failure. `iteration += 1` at the end of every failed loop.

---

## Output Format

### ✅ Success
```
✅ CloudFormation Template — Generated Successfully
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Iterations  : <N>
Gates passed: YAML ✅  CFN-Lint ✅  Deployment [✅ / ⏭️ skipped]
Saved to    : <path>

<full YAML template>
```

### ❌ Failure
```
❌ IaCGen — Max attempts reached
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Failed at   : <gate name>
Attempts    : YAML <N> / CFN-Lint <N> / Deploy <N>
Last error  : <error message>
Partial file: <path>
```

---

## Common CloudFormation Pitfalls

| Mistake | Correct Pattern |
|---|---|
| `DeletionPolicy` inside `Properties:` | Place at resource level, same indent as `Type:` |
| `BlockPublicAcls: true` with a public BucketPolicy | Set **all 4** `PublicAccessBlockConfiguration` fields to `false` |
| `!Select [ 0, !GetAZs '' ]` with spaces | `!Select [0, !GetAZs '']` — no spaces inside brackets |
| Lambda with no IAM execution role | Always include `AWS::IAM::Role` with `AWSLambdaBasicExecutionRole` |
| API Gateway with no Deployment + Stage | Always include `AWS::ApiGateway::Deployment` and `AWS::ApiGateway::Stage` |
| S3 website bucket with no BucketPolicy | Add `AWS::S3::BucketPolicy` with `s3:GetObject` Allow |
| RDS without a subnet group | `AWS::RDS::DBInstance` requires `AWS::RDS::DBSubnetGroup` in a VPC |
| IAM policy attached before role exists | Use `DependsOn:` or reference the role via `!GetAtt Role.Arn` |
