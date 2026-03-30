"""FreelancerEvolver: Evolve freelancer agent prompts for insight generation"""

import json
from typing import Optional
from datetime import datetime


class FreelancerEvolver:
    """Wraps freelancer agent for prompt evolution"""

    def __init__(self, agent_path: str = ".claude/agents/фрилансер"):
        """
        Args:
            agent_path: Path to freelancer agent directory
        """
        self.agent_path = agent_path
        self.current_prompt: Optional[str] = None
        self.original_prompt: Optional[str] = None
        self._load_prompt()

    def _load_prompt(self):
        """Load current prompt from agent config"""
        try:
            with open(f"{self.agent_path}/фрилансер.md", "r", encoding="utf-8") as f:
                content = f.read()
                # Extract the main instruction section
                self.original_prompt = content
                self.current_prompt = content
        except FileNotFoundError:
            raise FileNotFoundError(f"Agent file not found at {self.agent_path}/фрилансер.md")

    def get_current_prompt(self) -> str:
        """Get current prompt"""
        return self.current_prompt

    def set_prompt(self, prompt: str):
        """Set new prompt (simulated - doesn't modify actual file)"""
        self.current_prompt = prompt

    def solve(self, task: str) -> tuple[str, dict]:
        """
        Solve task using freelancer (simplified mock for evolution)

        In real scenario, this would call the actual agent through Claude API.
        For now, simulates analysis of the task.

        Returns:
            (insights_text, quality_metrics)
        """
        # Simulate solving based on task
        # In production: would call actual Claude Code agent
        insights = f"Analysis for task: {task}\n\n"
        insights += "Mock insights based on current prompt variant.\n"
        insights += "In production, this would call the actual freelancer agent."

        # Return mock metadata
        metadata = {
            "task": task,
            "timestamp": datetime.now().isoformat(),
            "prompt_length": len(self.current_prompt),
            "insight_count": 3,  # Mock value
        }

        return insights, metadata


def quality_score(result: str, metadata: dict) -> float:
    """
    Score quality of freelancer insights (0-1 scale)

    Evaluates:
    - Length (longer = more detailed)
    - Specificity (more metrics = better)
    - Clarity (simpler = better)

    Args:
        result: The insight text
        metadata: Associated metadata

    Returns:
        Quality score 0-1
    """
    score = 0.5  # Base score

    # Length metric: 200-800 chars is optimal
    length = len(result)
    if 200 <= length <= 800:
        score += 0.2
    elif 100 <= length <= 1000:
        score += 0.1

    # Specificity: count metrics mentioned
    metrics_keywords = ["metric", "insight", "pattern", "trend", "analyze"]
    metric_count = sum(result.lower().count(kw) for kw in metrics_keywords)
    score += min(0.3, metric_count * 0.05)

    # Clarity: simpler is better (fewer complex conjunctions)
    complexity = result.count(" therefore ") + result.count(" consequently ")
    score -= min(0.2, complexity * 0.1)

    return min(1.0, max(0.0, score))
