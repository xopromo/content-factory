#!/usr/bin/env python3
"""A-Evolve: Run freelancer agent prompt evolution"""

import sys
from a_evolve.freelancer_evolver import FreelancerEvolver, quality_score
from a_evolve.evolver import BaseEvolver


def main():
    """Run evolution process"""

    # Initialize freelancer agent
    print("🚀 Initializing A-Evolve Freelancer Evolution System\n")

    try:
        freelancer = FreelancerEvolver()
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("Make sure the freelancer agent exists at .claude/agents/фрилансер/")
        sys.exit(1)

    # Create evolver
    evolver = BaseEvolver(
        agent=freelancer,
        quality_fn=quality_score,
        mutation_rate=0.25
    )

    # Define task for evolution
    task = "Найди самые полезные инсайты для таргетирования на ВКонтакте. Ищи необычные паттерны и тренды."

    # Run evolution
    evolver.run(task=task, cycles=5, generations_per_cycle=3)

    # Save results
    save_evolution_results(evolver)


def save_evolution_results(evolver):
    """Save evolution results to file"""
    import json

    results = {
        "timestamp": evolver.history[0].metadata.get("timestamp") if evolver.history else None,
        "total_generations": len(evolver.history),
        "best_score": evolver.best_result.fitness_score if evolver.best_result else None,
        "best_cycle": evolver.best_result.cycle if evolver.best_result else None,
        "history": [
            {
                "cycle": r.cycle,
                "generation": r.generation,
                "score": r.fitness_score,
                "prompt_preview": r.prompt[:100] + "..." if len(r.prompt) > 100 else r.prompt,
            }
            for r in evolver.history
        ]
    }

    with open("evolution_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Results saved to evolution_results.json")


if __name__ == "__main__":
    main()
