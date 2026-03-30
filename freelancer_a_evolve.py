"""A-Evolve integration for freelancer VK targeting insights agent"""

import json
import logging
from pathlib import Path
from typing import Optional
import agent_evolve as ae
from agent_evolve.types import Task, Feedback, Trajectory


logger = logging.getLogger(__name__)


class FreelancerAgent(ae.BaseAgent):
    """Agent for finding VK targeting insights - compatible with A-Evolve"""

    def __init__(self, workspace_path: str):
        """
        Args:
            workspace_path: Path to freelancer workspace with prompts, skills, memory
        """
        super().__init__(workspace_path)
        self.workspace = Path(workspace_path)
        self.prompts_dir = self.workspace / "prompts"
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load system prompt from workspace"""
        prompt_file = self.prompts_dir / "system.md"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return "You are a VK targeting insights specialist."

    def solve(self, task: Task) -> Trajectory:
        """
        Solve a task about VK targeting insights

        Args:
            task: A-Evolve Task with input and metadata

        Returns:
            Trajectory with output and steps
        """
        try:
            # For now, simulate insight generation
            # In production: would call Claude API with the system prompt
            query = task.input

            # Mock analysis based on query
            insights = self._generate_insights(query)

            return Trajectory(
                task_id=task.id,
                output=insights,
                steps=[
                    {
                        "type": "analysis",
                        "query": query,
                        "insight_count": len(insights.split("💡")) - 1,
                        "status": "success"
                    }
                ]
            )

        except Exception as e:
            logger.error(f"Error solving task {task.id}: {e}")
            return Trajectory(
                task_id=task.id,
                output="",
                steps=[{"error": str(e)}]
            )

    def _generate_insights(self, query: str) -> str:
        """Generate mock insights about VK targeting"""
        # In production, this would:
        # 1. Use WebSearch to find relevant info
        # 2. Analyze with system_prompt
        # 3. Return structured insights

        return f"""VK Targeting Analysis for: {query}

💡 **Insight 1: Audience Interest Targeting**
📊 Analysis: VK's algorithm rewards specificity - targeting 3-5 interest categories outperforms broad targeting
✅ Application: Choose niche interests related to your product, test combinations
⭐ Impact: high
🔗 Based on internal VK docs

💡 **Insight 2: Demographic Optimization**
📊 Analysis: Age ranges work better than exact ages - 25-35 age bracket targets more efficiently than specific years
✅ Application: Use age ranges instead of year-by-year targeting
⭐ Impact: medium
🔗 Industry best practices

💡 **Insight 3: Geographic Precision**
📊 Analysis: City-level targeting is more cost-effective than regional targeting for VK
✅ Application: Target specific cities rather than entire regions
⭐ Impact: medium
🔗 Observed in campaign data
"""

    @property
    def manifest_path(self) -> Path:
        """Get manifest path"""
        return self.workspace / "manifest.yaml"


class FreelancerBenchmark(ae.BenchmarkAdapter):
    """Evaluate quality of freelancer insights"""

    def __init__(self):
        """Initialize benchmark with scoring criteria"""
        self.name = "freelancer-insights"
        self.task_count = 5  # Use 5 test tasks

    def get_tasks(self, split: str = "train", limit: int = 10) -> list[Task]:
        """Get benchmark tasks for freelancer evaluation"""
        tasks = [
            Task(
                id="vk-targeting-001",
                input="Найди самые полезные инсайты для таргетирования в ВКонтакте",
                metadata={"domain": "vk-ads", "difficulty": "medium"}
            ),
            Task(
                id="vk-targeting-002",
                input="Какие необычные паттерны в поведении пользователей ВК?",
                metadata={"domain": "vk-ads", "difficulty": "hard"}
            ),
            Task(
                id="vk-targeting-003",
                input="Как оптимизировать таргет по возрасту и интересам на ВК?",
                metadata={"domain": "vk-ads", "difficulty": "medium"}
            ),
            Task(
                id="vk-targeting-004",
                input="Найди ошибки в таргетировании, которые делают новички на ВК",
                metadata={"domain": "vk-ads", "difficulty": "easy"}
            ),
            Task(
                id="vk-targeting-005",
                input="Какие геолокационные стратегии работают лучше всего на ВК?",
                metadata={"domain": "vk-ads", "difficulty": "medium"}
            ),
        ]
        return tasks

    def score(self, output: str, task: Task) -> float:
        """
        Score quality of insights (0-1 scale)

        Criteria:
        - Presence of multiple insights (3+ is good)
        - Structured format with analysis and applications
        - Specificity to VK platform
        - Actionability of recommendations
        """
        score = 0.5  # Base score

        # Count insights
        insight_count = output.count("💡")
        if insight_count >= 3:
            score += 0.2
        elif insight_count >= 2:
            score += 0.1

        # Check for analysis sections
        if "📊 Analysis:" in output:
            score += 0.15
        if "✅ Application:" in output:
            score += 0.15

        # Check for impact levels
        impacts = output.count("⭐ Impact:")
        if impacts >= 2:
            score += 0.1

        # Bonus for length (more detailed = better)
        if len(output) > 500:
            score += 0.05

        # Penalty for generic responses
        if "I don't know" in output or "Unable to" in output:
            score = max(0.1, score - 0.3)

        return min(1.0, score)

    def evaluate(self, task: Task, trajectory: Trajectory) -> Feedback:
        """
        Evaluate trajectory and provide feedback

        Args:
            task: Original task
            trajectory: Agent output

        Returns:
            Feedback with score and suggestions
        """
        score = self.score(trajectory.output, task)

        feedback_text = ""
        if score < 0.3:
            feedback_text = "Output lacks specific insights. Provide more concrete examples."
        elif score < 0.6:
            feedback_text = "Good start but needs more structured analysis and applications."
        elif score < 0.8:
            feedback_text = "Strong insights. Consider adding more VK-specific metrics."
        else:
            feedback_text = "Excellent structured insights with clear applications."

        return Feedback(
            success=score > 0.5,
            score=score,
            detail=feedback_text,
            raw={"task_id": task.id, "output_length": len(trajectory.output)}
        )
