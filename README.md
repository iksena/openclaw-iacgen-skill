# openclaw-iacgen-skill

An [OpenClaw](https://openclaw.ai) Agent Skill that replicates the **IaCGen** framework
([Zhang et al., FSE 2025](https://arxiv.org/abs/2506.05623)) as a modular, agent-native
capability.

In the original IaCGen, a Python orchestrator calls an external LLM to generate
CloudFormation templates. In this OpenClaw Skill, **the agent itself is the LLM
generator** — `SKILL.md` teaches it the IaCGen prompting methodology and three
sequential validation gates via helper scripts.

## How It Works

```
User prompt
    │
    ▼
Agent generates CloudFormation YAML  (IaCGen chain-of-thought prompting)
    │
    ▼
Gate 1 — validate_yaml.py    ──FAIL──►  fix YAML structure → retry
    │ PASS
    ▼
Gate 2 — validate_cfn.py     ──FAIL──►  fix CloudFormation schema errors → retry
    │ PASS
    ▼
Gate 3 — deploy_aws.py       ──FAIL──►  fix runtime AWS conflicts → retry
    │ PASS
    ▼
Return final YAML + deployment confirmation
```

Feedback escalates across 3 levels per gate (matching IaCGen's original logic):

| Attempts | Feedback level | What the agent gets |
|---|---|---|
| 0–1 | **Simple** | Gate name only: "cfn-lint errors found; fix them" |
| 2–5 | **Moderate** | Full `error_details` list with resource, message, line, rule |
| 6–9 | **Advanced** | `documentation` URL per error for exact AWS property constraints |
| 10 | **Stop** | `max_attempts_exceeded` → return failure |

## File Structure

```
openclaw-iacgen-skill/
├── SKILL.md                    ←  AgentSkills-compatible skill definition (loaded into agent)
├── README.md
└── scripts/
    ├── validate_yaml.py        ←  Gate 1: yamllint (structural YAML correctness)
    ├── validate_cfn.py         ←  Gate 2: cfn-lint (CloudFormation schema validation)
    └── deploy_aws.py           ←  Gate 3: boto3 live CloudFormation deployment
```

## Installation

### 1. Install Python dependencies

```bash
pip install cfn-lint yamllint boto3
```

### 2. Install the skill into OpenClaw

```bash
# Option A — global install (available to all agents on this machine)
git clone https://github.com/iksena/openclaw-iacgen-skill ~/.openclaw/skills/iacgen

# Option B — workspace install (current agent only)
git clone https://github.com/iksena/openclaw-iacgen-skill ./skills/iacgen

# Option C — via ClawHub (once published)
clawhub install iacgen
```

### 3. Set AWS credentials *(optional — enables Gate 3 live deployment)*

```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

> Gate 3 is **automatically skipped** if AWS credentials are not set.
> You still get fully YAML-validated and cfn-lint-validated templates.

## Usage

Once installed, just describe your infrastructure need:

```
You: Generate a CloudFormation template for an S3 bucket with website hosting
     and a DeletionPolicy.

Agent: [Runs IaCGen skill → generates template → validates → returns final YAML]
```

```
You: Create IaC for a Lambda function behind API Gateway with DynamoDB storage.

Agent: [Identifies 7+ resource types → iterates through gates → returns
        deployable template]
```

## How This Compares to the Original IaCGen

| Aspect | Original IaCGen | This OpenClaw Skill |
|---|---|---|
| LLM | External API (Claude / GPT / Gemini / DeepSeek) | OpenClaw's configured model (agent itself) |
| Orchestration | `main.py` Python `while` loop | `SKILL.md` instructions + agent reasoning |
| Gate 1 YAML | `yamllint` library | `validate_yaml.py` (same library) |
| Gate 2 CFN-Lint | `cfn-lint` subprocess | `validate_cfn.py` (same tool) |
| Gate 3 Deploy | `boto3` CloudFormation client | `deploy_aws.py` (same API) |
| Feedback levels | simple / moderate / advanced | Same 3-level escalation, same counter logic |
| Batch benchmark | Yes (`start_row`/`end_row` over a CSV) | ❌ Interactive, one request at a time |
| Results CSV | Yes (`Result/iterative_*.csv`) | ❌ Agent reports inline |

## Security Notes

- Gate 3 creates **real AWS resources** that incur costs. Stacks are deleted immediately
  after validation, but failed stacks may linger in `ROLLBACK_COMPLETE`. Monitor your
  AWS account and set a billing alert.
- Use a dedicated IAM user with least-privilege: CloudFormation stack create/delete +
  the resource types you intend to test.
- **Never commit AWS credentials** to this repository.

## References

- Zhang et al. (2025). *Deployability-Centric Infrastructure-as-Code Generation: Fail,
  Learn, Refine, and Succeed through LLM-Empowered DevOps Simulation.* FSE 2025.
  [arXiv:2506.05623](https://arxiv.org/abs/2506.05623)
- OpenClaw Skill format: [docs.openclaw.ai/tools/skills](https://docs.openclaw.ai/tools/skills)
- AgentSkills SoK: [arxiv.org/abs/2602.20867](https://arxiv.org/abs/2602.20867)
