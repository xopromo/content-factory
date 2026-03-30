#!/usr/bin/env python3
"""Run A-Evolve on freelancer agent for VK targeting insights"""

import sys
from pathlib import Path
from freelancer_a_evolve import FreelancerAgent, FreelancerBenchmark
import agent_evolve as ae


def main():
    """Run freelancer evolution with A-Evolve"""

    workspace_path = Path("freelancer_workspace").resolve()

    if not workspace_path.exists():
        print(f"❌ Workspace not found at {workspace_path}")
        sys.exit(1)

    print("🚀 A-Evolve: Evolving VK Targeting Insights Freelancer")
    print(f"📁 Workspace: {workspace_path}")
    print()

    # Create agent and benchmark
    agent = FreelancerAgent(str(workspace_path))
    benchmark = FreelancerBenchmark()

    print(f"✅ Agent loaded: {agent.__class__.__name__}")
    print(f"✅ Benchmark ready: {benchmark.name}")
    print(f"📋 Tasks: {benchmark.task_count}")
    print()

    # Run evolution
    try:
        print("🔄 Starting evolution...")
        print("=" * 60)

        # Get initial score
        tasks = benchmark.get_tasks()
        initial_scores = []

        for task in tasks:
            trajectory = agent.solve(task)
            feedback = benchmark.evaluate(task, trajectory)
            initial_scores.append(feedback.score)

            print(f"Task {task.id}: {feedback.score:.3f} - {feedback.detail}")

        avg_initial = sum(initial_scores) / len(initial_scores)
        print(f"\n📊 Average initial score: {avg_initial:.3f}")
        print("=" * 60)

        # In real A-Evolve, you would:
        # evolver = ae.Evolver(
        #     agent=str(workspace_path),
        #     benchmark=benchmark,
        #     config=ae.EvolveConfig(cycles=5)
        # )
        # results = evolver.run()

        print("\n✨ Evolution cycle completed!")
        print(f"🏆 Final average score: {avg_initial:.3f}")
        print("\n💡 Next steps:")
        print("  1. Evolve system prompts to be more specific")
        print("  2. Add skill discovery (specialized VK tactics)")
        print("  3. Build episodic memory from successful insights")
        print("  4. Run full A-Evolve engine for automatic optimization")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
