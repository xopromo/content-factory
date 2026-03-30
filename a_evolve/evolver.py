"""Base evolution engine for agent prompt optimization"""

import json
import random
from dataclasses import dataclass, asdict
from typing import Protocol, Any, Optional
from datetime import datetime


@dataclass
class EvolutionResult:
    """Result of an evolution cycle"""
    cycle: int
    generation: int
    fitness_score: float
    prompt: str
    metadata: dict = None


class Agent(Protocol):
    """Protocol for agents that can be evolved"""

    def solve(self, task: str) -> tuple[str, dict]:
        """
        Solve a task and return result with metadata

        Returns:
            (result_text, metadata_dict)
        """
        ...


class BaseEvolver:
    """Evolves agent prompts through mutation and selection"""

    def __init__(self, agent: Agent, quality_fn, mutation_rate: float = 0.3):
        """
        Args:
            agent: Agent with solve(task) method
            quality_fn: Function that scores output (0-1 scale)
            mutation_rate: Probability of mutating each word (0-1)
        """
        self.agent = agent
        self.quality_fn = quality_fn
        self.mutation_rate = mutation_rate
        self.best_result: Optional[EvolutionResult] = None
        self.history: list[EvolutionResult] = []

    def mutate_prompt(self, prompt: str) -> str:
        """Apply random mutations to prompt"""
        words = prompt.split()
        mutations = [
            self._add_adjective,
            self._strengthen_verb,
            self._reorder_phrase,
        ]

        for i, word in enumerate(words):
            if random.random() < self.mutation_rate:
                mutation = random.choice(mutations)
                word = mutation(word)
                words[i] = word

        return " ".join(words)

    def _add_adjective(self, word: str) -> str:
        """Add intensifying adjective"""
        adjectives = ["more", "better", "clearer", "concrete", "specific"]
        return f"{random.choice(adjectives)} {word}"

    def _strengthen_verb(self, word: str) -> str:
        """Strengthen action verbs"""
        replacements = {
            "find": "discover and analyze",
            "get": "extract",
            "make": "create and optimize",
            "show": "highlight and explain",
            "give": "provide detailed",
        }
        return replacements.get(word, word)

    def _reorder_phrase(self, word: str) -> str:
        """Reorder for clarity"""
        return word  # Simplified for now

    def run_cycle(self, task: str, num_generations: int = 3) -> EvolutionResult:
        """Run one evolution cycle with multiple generations"""
        print(f"\n🔄 Evolution Cycle {len(self.history) // num_generations + 1}")

        cycle_num = len(self.history) // num_generations + 1
        best_cycle_result = None

        for gen in range(num_generations):
            # Get current prompt (mutated version)
            current_prompt = self.agent.get_current_prompt()
            mutated_prompt = self.mutate_prompt(current_prompt)

            # Test mutated prompt
            self.agent.set_prompt(mutated_prompt)
            result, metadata = self.agent.solve(task)

            # Score result
            score = self.quality_fn(result, metadata)

            evolution_result = EvolutionResult(
                cycle=cycle_num,
                generation=gen + 1,
                fitness_score=score,
                prompt=mutated_prompt,
                metadata=metadata
            )

            self.history.append(evolution_result)

            print(f"  Gen {gen + 1}: score={score:.3f}")

            # Keep best result
            if best_cycle_result is None or score > best_cycle_result.fitness_score:
                best_cycle_result = evolution_result

                # Update agent if this is better than best ever
                if self.best_result is None or score > self.best_result.fitness_score:
                    self.best_result = evolution_result
                    self.agent.set_prompt(mutated_prompt)
                    print(f"  ✨ New best! Score: {score:.3f}")

        return best_cycle_result

    def run(self, task: str, cycles: int = 5, generations_per_cycle: int = 3):
        """Run full evolution"""
        print(f"\n🚀 Starting A-Evolve: {cycles} cycles, {generations_per_cycle} gen/cycle")
        print(f"Task: {task}\n")

        for cycle in range(cycles):
            self.run_cycle(task, generations_per_cycle)

        self._print_summary()

    def _print_summary(self):
        """Print evolution results"""
        print("\n" + "="*60)
        print("📊 EVOLUTION SUMMARY")
        print("="*60)

        if self.best_result:
            print(f"\n🏆 Best Result (Score: {self.best_result.fitness_score:.3f})")
            print(f"Cycle {self.best_result.cycle}, Gen {self.best_result.generation}")
            print(f"\nOptimized Prompt:\n{self.best_result.prompt}")

            if self.best_result.metadata:
                print(f"\nMetadata: {json.dumps(self.best_result.metadata, indent=2)}")

        print(f"\nTotal generations tested: {len(self.history)}")

        # Show score progression
        scores = [r.fitness_score for r in self.history]
        print(f"Score range: {min(scores):.3f} - {max(scores):.3f}")
