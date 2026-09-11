import logging
from pathlib import Path
from typing import Optional
import git

logger = logging.getLogger(__name__)


class GitTool:
    """
    Git operations scoped to a specific repo path.
    Read operations are L0 (automatic).
    Commit is L2 (logged, optional approval).
    Push is L3 (requires HITL approval) — not implemented here, goes through governance.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()

    def _repo(self) -> git.Repo:
        return git.Repo(str(self.repo_path))

    def get_diff(self, staged: bool = False) -> str:
        repo = self._repo()
        if staged:
            return repo.git.diff("--cached")
        return repo.git.diff()

    def get_recent_commits(self, count: int = 5) -> list:
        repo = self._repo()
        return [
            {
                "hash": c.hexsha[:8],
                "message": c.message.strip(),
                "author": str(c.author),
                "date": c.committed_datetime.isoformat(),
            }
            for c in repo.iter_commits(max_count=count)
        ]

    def get_status(self) -> dict:
        repo = self._repo()
        return {
            "branch": repo.active_branch.name,
            "modified": [item.a_path for item in repo.index.diff(None)],
            "untracked": repo.untracked_files,
            "staged": [item.a_path for item in repo.index.diff("HEAD")],
        }

    def create_branch(self, branch_name: str) -> None:
        repo = self._repo()
        repo.git.checkout("-b", branch_name)
        logger.info(f"Created branch: {branch_name}")

    def commit(self, message: str, files: Optional[list] = None) -> str:
        repo = self._repo()
        if files:
            repo.index.add(files)
        else:
            repo.git.add(".")
        commit = repo.index.commit(message)
        logger.info(f"Committed: {commit.hexsha[:8]} — {message}")
        return commit.hexsha
