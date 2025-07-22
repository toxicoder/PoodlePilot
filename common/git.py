from functools import cache
import subprocess
from typing import Optional, List

# Assuming run_cmd and run_cmd_default from openpilot.common.run return str
# and their cwd parameter is Optional[str].
# If their signatures are different, these annotations might need adjustment
# or type: ignore might be needed for their calls.
from openpilot.common.run import run_cmd, run_cmd_default


@cache
def get_commit(cwd: Optional[str] = None, branch: str = "HEAD") -> str:
  # run_cmd_default is assumed to take List[str] as its first argument
  return run_cmd_default(["git", "rev-parse", branch], cwd=cwd)


@cache
def get_commit_date(cwd: Optional[str] = None, commit: str = "HEAD") -> str:
  return run_cmd_default(["git", "show", "--no-patch", "--format='%ct %ci'", commit], cwd=cwd)


@cache
def get_short_branch(cwd: Optional[str] = None) -> str:
  return run_cmd_default(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)


@cache
def get_branch(cwd: Optional[str] = None) -> str:
  # This command can fail if not on a branch or no upstream is set.
  # The original code doesn't handle this failure explicitly here, relying on run_cmd_default.
  # For typing, we assume it returns str or run_cmd_default handles errors by raising or returning default.
  return run_cmd_default(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=cwd)


@cache
def get_origin(cwd: Optional[str] = None) -> str:
  try:
    # Assuming run_cmd returns str
    local_branch: str = run_cmd(["git", "name-rev", "--name-only", "HEAD"], cwd=cwd)
    tracking_remote: str = run_cmd(["git", "config", "branch." + local_branch + ".remote"], cwd=cwd)
    return run_cmd(["git", "config", "remote." + tracking_remote + ".url"], cwd=cwd)
  except subprocess.CalledProcessError:  # Not on a branch, fallback
    return run_cmd_default(["git", "config", "--get", "remote.origin.url"], cwd=cwd)


@cache
def get_normalized_origin(cwd: Optional[str] = None) -> str:
  origin_url: str = get_origin(cwd)
  return origin_url \
    .replace("git@", "", 1) \
    .replace(".git", "", 1) \
    .replace("https://", "", 1) \
    .replace(":", "/", 1)
