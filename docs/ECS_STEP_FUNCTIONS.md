# Running infogen on ECS from a Step Functions state machine

On ECS there is no API server and no instance. Each run of the Claude session is one Fargate task, started by a state machine
(owned by StoryStudio) with `ecs:runTask.waitForTaskToken`. The task starts the job or resumes it after a checkpoint, follows
it until Claude stops (at a checkpoint, or at the end), and reports the status object back with `SendTaskSuccess`.
Approval at the checkpoints stays in the state machine, between two tasks. Entry point: `python3 -m api.task` (see its docstring).

Unchanged from the HTTP API: the request body, the status object, stage names, checkpoint ids (`cp_script`, `cp_final`),
output kinds, the S3 upload under `infogen/<request_id>/`, and the signed `X-Infogen-*` webhooks (still sent, with `seq`
continuing across tasks; each task waits until its webhooks are delivered before it exits).

## AWS resources (us-east-1)

| Resource | Name | Notes |
|---|---|---|
| ECR repository | `infogen` | Built by CodeBuild `infogen-image` (`buildspec.yml`), tags `<commit>` and `latest`. |
| ECS cluster | `infogen` | Fargate only. One cluster per service, like `qm-shorts-longform`. |
| Task definition | `infogen-worker` | ARM64 (`runtimePlatform.cpuArchitecture: ARM64`), container `infogen`, entry point `python3 -m api.task`, image `infogen:latest`. |
| EFS file system | `infogen-data` | Holds run folders and Claude sessions between tasks. Access points `/runs` -> `/data/runs`, `/claude` -> `/data/claude`, both uid/gid 1000. Mount targets in the subnets below. |
| Security group | `infogen-task` | No inbound rules; all outbound. EFS mount targets get `infogen-efs` admitting NFS (2049) from `infogen-task` only. |
| Execution role | `infogen-task-execution` | Pull from the `infogen` ECR repository, write the log group `/ecs/infogen`, read `/infogen/*` parameters (secrets). |
| Task role | `infogen-task` | `s3:PutObject` on `storystudio-unified-storage-prod/infogen/*`; `states:SendTaskSuccess`, `SendTaskFailure`, `SendTaskHeartbeat`; EFS client mount/write on the access points. |

Network: the default VPC's public subnets with `AssignPublicIp: ENABLED`, like the other StoryStudio tasks. Outbound access is
needed for Anthropic, WebSearch/WebFetch, Gemini, RunPod, ComfyUI, ECR, SSM, S3, Step Functions and the webhook URL.

Secrets (task definition `secrets`, from SSM): `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `RUNPOD_API_KEY`, `COMFY_API_KEY`,
`INFOGEN_CALLBACK_SECRET`. Plain environment: `INFOGEN_OUTPUT_BUCKET=storystudio-unified-storage-prod`,
`INFOGEN_OUTPUT_BASE_URL=https://cdn-v2.ai-storystudio.com`, `ANTHROPIC_MODEL=claude-sonnet-5-5`, `INFOGEN_RUNNER=claude`.
`INFOGEN_API_TOKEN`, `INFOGEN_ORIGIN_SECRET` and `VNC_PASSWORD` are not used on ECS.

Size: the start task (research and scripts, until `cp_script`) needs little: 2 vCPU / 4 GB. The task after `cp_script` is
approved renders the videos and is CPU-bound: 16 vCPU / 32 GB. Override `Cpu`/`Memory` per RunTask (task-level overrides).

## The task

Container overrides:

| Variable | Value |
|---|---|
| `PAYLOAD_JSON` | start: `{"request": {...}}` (the body of `POST /v1/infographics`). Resume: `{"job_id": "ig_...", "response": {"checkpoint_id": "cp_script", "action": "approve" \| "revise" \| "abort", "instructions": ""}}` |
| `INFOGEN_TASK_TOKEN` | `$$.Task.Token` |

Result:

- `SendTaskSuccess`, output = the status object. `state` is `awaiting_input` (then `awaiting.checkpoint_id`, `awaiting.question`,
  `awaiting.review` say what to show the reviewer), `succeeded` (with `outputs` and `costs`) or `cancelled` (after `abort`).
- `SendTaskFailure`, `error` = the error code (`invalid_request`, `duplicate_request`, `not_found`, `not_awaiting_input`,
  `wrong_checkpoint`, `not_ready`, `generation_failed`, `llm_error`, `timeout`, `internal`), `cause` = the status object as JSON.
- `SendTaskHeartbeat` every 60 s. Set `HeartbeatSeconds` (for example 600) so a task that dies without reporting
  (out of memory, stopped by ECS) fails the state instead of waiting for ever.

`limits.max_runtime_minutes` applies to each task separately; the time a job waits at a checkpoint does not count.

## State machine (outline)

```json
{
  "StartAt": "Start",
  "States": {
    "Start": {
      "Type": "Task", "Resource": "arn:aws:states:::ecs:runTask.waitForTaskToken",
      "Parameters": {
        "Cluster": "infogen", "TaskDefinition": "infogen-worker", "LaunchType": "FARGATE",
        "NetworkConfiguration": {"AwsvpcConfiguration": {"Subnets": ["subnet-02557f42e07118380", "subnet-0389bf7ebb5a497ac"],
                                                         "SecurityGroups": ["<infogen-task>"], "AssignPublicIp": "ENABLED"}},
        "Overrides": {"Cpu": "2048", "Memory": "4096", "ContainerOverrides": [{"Name": "infogen", "Environment": [
          {"Name": "PAYLOAD_JSON", "Value.$": "States.JsonToString($.payload)"},
          {"Name": "INFOGEN_TASK_TOKEN", "Value.$": "$$.Task.Token"}]}]}
      },
      "HeartbeatSeconds": 600, "TimeoutSeconds": 14400, "ResultPath": "$.job", "Next": "Route"
    },
    "Route": {"Type": "Choice", "Choices": [
        {"Variable": "$.job.state", "StringEquals": "awaiting_input", "Next": "Review"},
        {"Variable": "$.job.state", "StringEquals": "succeeded", "Next": "Done"},
        {"Variable": "$.job.state", "StringEquals": "cancelled", "Next": "Cancelled"}], "Default": "Failed"},
    "Review": {
      "Comment": "StoryStudio's approval step: send $.job.awaiting and $$.Task.Token to the reviewer; their answer comes back with SendTaskSuccess(output = {checkpoint_id, action, instructions}).",
      "Type": "Task", "Resource": "<StoryStudio's .waitForTaskToken integration>", "ResultPath": "$.response", "Next": "Size"
    },
    "Size": {"Type": "Choice", "Choices": [
        {"And": [{"Variable": "$.response.checkpoint_id", "StringEquals": "cp_script"}, {"Variable": "$.response.action", "StringEquals": "approve"}], "Next": "ResumeLarge"}],
      "Default": "ResumeSmall"},
    "ResumeLarge": {"Comment": "as Start, with Cpu 16384 / Memory 32768 and PAYLOAD_JSON = {job_id: $.job.job_id, response: $.response}", "Type": "Task", "...": "...", "Next": "Route"},
    "ResumeSmall": {"Comment": "as Start, with Cpu 2048 / Memory 4096 and the same payload", "Type": "Task", "...": "...", "Next": "Route"},
    "Done": {"Type": "Succeed"}, "Cancelled": {"Type": "Succeed"}, "Failed": {"Type": "Fail"}
  }
}
```

The resume payload is built with `States.JsonToString(States.JsonMerge(...))` or a `Pass` state that sets
`{"job_id.$": "$.job.job_id", "response.$": "$.response"}` before the resume task. A revise loops through `Review` again.
Add `Catch` on the task states (`States.ALL` -> a failure handler that reads `Cause`).
