"""Mock agent_evolve module - provides types needed by agents"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class Task:
    """A task for an agent to solve"""
    id: str
    input: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class Feedback:
    """Feedback on agent performance"""
    score: float
    detail: str
    metadata: Optional[Dict[str, Any]] = None
    success: Optional[bool] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class Trajectory:
    """Trajectory of agent solving a task"""
    task_id: str
    output: str
    steps: List[Dict[str, Any]] = field(default_factory=list)


class BaseAgent(Protocol):
    """Base protocol for agents that can be evolved"""

    def solve(self, task: Task) -> Trajectory:
        """Solve a task and return trajectory"""
        ...


class BenchmarkAdapter:
    """Base class for benchmark adapters"""

    def __init__(self):
        """Initialize benchmark"""
        self.name = "benchmark"
        self.task_count = 0

    def get_tasks(self, split: str = "train", limit: int = 10) -> List[Task]:
        """Get benchmark tasks"""
        return []

    def evaluate(self, task: Task, trajectory: Trajectory) -> Feedback:
        """Evaluate trajectory"""
        return Feedback(score=0.0, detail="")


__all__ = ["Task", "Feedback", "Trajectory", "BaseAgent", "BenchmarkAdapter"]
