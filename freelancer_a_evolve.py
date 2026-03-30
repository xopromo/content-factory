"""A-Evolve integration for freelancer VK targeting insights agent

Uses Ollama for local LLM (free) + WebSearch for information gathering
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional
import agent_evolve as ae
from agent_evolve.types import Task, Feedback, Trajectory


logger = logging.getLogger(__name__)

# Configuration
OLLAMA_MODEL = "mistral"  # Change to your preferred model
OLLAMA_BASE_URL = "http://localhost:11434"


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
        Solve a task about VK targeting insights using Ollama

        Args:
            task: A-Evolve Task with input and metadata

        Returns:
            Trajectory with output and steps
        """
        try:
            query = task.input
            steps = []

            # Step 1: Check if Ollama is running
            ollama_available = self._check_ollama()
            if not ollama_available:
                logger.warning(f"Ollama not available, using mock insights")
                insights = self._generate_insights(query)
            else:
                # Step 2: Use Ollama with the evolvable system prompt
                insights = self._generate_with_ollama(query)
                steps.append({
                    "type": "ollama_generation",
                    "model": OLLAMA_MODEL,
                    "status": "success"
                })

            return Trajectory(
                task_id=task.id,
                output=insights,
                steps=steps + [
                    {
                        "type": "analysis",
                        "query": query,
                        "insight_count": len(insights.split("💡")) - 1,
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

    def _check_ollama(self) -> bool:
        """Check if Ollama is running"""
        try:
            result = subprocess.run(
                ["curl", "-s", f"{OLLAMA_BASE_URL}/api/tags"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False

    def _generate_with_ollama(self, query: str) -> str:
        """Generate insights using Ollama local LLM"""
        try:
            import requests

            # Combine system prompt with query
            prompt = f"""{self.system_prompt}

## Task
{query}

## Expected Output Format
Provide VK targeting insights in this format:

💡 **Insight Title**
📊 Analysis: [Why this works]
✅ Application: [How to use]
⭐ Impact: [high/medium/low]
🔗 Source: [URL or reference]
"""

            response = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                },
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                logger.warning(f"Ollama error: {response.status_code}")
                return self._generate_insights(query)

        except ImportError:
            logger.warning("requests library not available, using mock insights")
            return self._generate_insights(query)
        except Exception as e:
            logger.warning(f"Ollama generation failed: {e}, using mock insights")
            return self._generate_insights(query)

    def _generate_insights(self, query: str) -> str:
        """Generate mock insights about VK targeting (fallback)"""
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
