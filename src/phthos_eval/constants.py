SCHEMA_VERSION = "0.2.0"

CHANGE_CLASSES = ("prompt", "tool", "policy", "model", "finetune_data", "none")
FAILURE_TYPES = ("wrong_tool", "loop", "budget", "policy")

FAILURE_TO_CHANGE_CLASS = {
    "policy": "policy",
    "wrong_tool": "tool",
    "budget": "model",
    "loop": "prompt",
}
