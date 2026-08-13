SCHEMA_VERSION = "0.1.0"

CHANGE_CLASSES = ("prompt", "tool", "policy", "model", "finetune_data", "none")
FAILURE_TYPES = ("wrong_tool", "loop", "budget", "policy")

# First matching failure type wins.
FAILURE_TO_CHANGE_CLASS = {
    "policy": "policy",
    "wrong_tool": "tool",
    "budget": "model",
    "loop": "prompt",
}
