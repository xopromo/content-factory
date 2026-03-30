#!/usr/bin/env python3
"""A-Evolve: Run freelancer agent prompt evolution with detailed logging"""

import sys
import json
from pathlib import Path
from datetime import datetime
from freelancer_a_evolve import FreelancerAgent, FreelancerBenchmark
import agent_evolve as ae


def log_prompt_change(agent, cycle_num, gen_num, old_prompt, new_prompt, score):
    """Log prompt mutations for tracking"""
    log_file = Path("evolution_log.jsonl")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "cycle": cycle_num,
        "generation": gen_num,
        "score": score,
        "old_prompt_length": len(old_prompt),
        "new_prompt_length": len(new_prompt),
        "prompt_diff": {
            "old": old_prompt[:200] + "..." if len(old_prompt) > 200 else old_prompt,
            "new": new_prompt[:200] + "..." if len(new_prompt) > 200 else new_prompt,
        }
    }

    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    """Run freelancer evolution with detailed logging"""

    workspace_path = Path("freelancer_workspace").resolve()

    if not workspace_path.exists():
        print(f"❌ Workspace not found at {workspace_path}")
        sys.exit(1)

    print("\n" + "="*70)
    print("🚀 A-EVOLVE: VK Targeting Insights Freelancer Evolution")
    print("="*70)
    print(f"📁 Workspace: {workspace_path}")
    print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Create agent and benchmark
    print("📦 Initializing components...")
    agent = FreelancerAgent(str(workspace_path))
    benchmark = FreelancerBenchmark()

    print(f"  ✅ Agent: {agent.__class__.__name__}")
    print(f"  ✅ Benchmark: {benchmark.name}")
    print(f"  ✅ Test tasks: {benchmark.task_count}")
    print()

    # Run evolution
    try:
        print("="*70)
        print("PHASE 1: BASELINE EVALUATION")
        print("="*70)
        print()

        # Get initial score
        tasks = benchmark.get_tasks()
        initial_scores = []

        print("🧪 Testing baseline freelancer on all tasks...")
        print()

        for i, task in enumerate(tasks, 1):
            print(f"  [{i}/{len(tasks)}] Task: {task.id}")
            print(f"       Input: {task.input[:60]}...")

            trajectory = agent.solve(task)
            feedback = benchmark.evaluate(task, trajectory)
            initial_scores.append(feedback.score)

            status = "✅" if feedback.score > 0.7 else "⚠️" if feedback.score > 0.4 else "❌"
            print(f"       Score: {feedback.score:.3f} {status}")
            print(f"       Feedback: {feedback.detail}")
            print()

        avg_initial = sum(initial_scores) / len(initial_scores)

        print("="*70)
        print("📊 BASELINE RESULTS")
        print("="*70)
        print(f"Average score: {avg_initial:.3f}")
        print(f"Min score: {min(initial_scores):.3f}")
        print(f"Max score: {max(initial_scores):.3f}")
        print()

        # Show current prompt
        print("="*70)
        print("📄 CURRENT SYSTEM PROMPT (baseline)")
        print("="*70)
        print(agent.system_prompt[:500])
        print("...")
        print()

        print("="*70)
        print("PHASE 2: EVOLUTION - PROMPT MUTATIONS")
        print("="*70)
        print()

        # Evolution cycles
        evolution_cycles = 5
        print(f"🧬 Running {evolution_cycles} evolution cycles...")
        print(f"   Each cycle: mutate → evaluate → decide")
        print()

        cycle_scores = [avg_initial]
        best_prompt = agent.system_prompt
        best_score = avg_initial

        for cycle in range(1, evolution_cycles + 1):
            print(f"\n{'='*70}")
            print(f"CYCLE {cycle}/{evolution_cycles}")
            print(f"{'='*70}")

            # Show current prompt state
            print(f"\n📄 Current prompt (before mutation):")
            print(f"   Length: {len(agent.system_prompt)} chars")
            print(f"   Preview: {agent.system_prompt[:100]}...")
            print()

            # Simulate mutation
            print(f"🔀 Mutating system prompt...")

            # Different mutations per cycle
            mutations = [
                ("Add specificity", "Добавить более конкретные инструкции"),
                ("Strengthen analysis", "Усилить аналитический подход"),
                ("Focus on uniqueness", "Сосредоточиться на уникальности"),
                ("Add practical examples", "Добавить практические примеры"),
                ("Improve structure", "Улучшить структуру выходных данных"),
            ]

            mutation_type, mutation_desc = mutations[cycle - 1] if cycle <= len(mutations) else ("Generic improvement", "Общее улучшение")

            print(f"   Type: {mutation_type}")
            print(f"   Description: {mutation_desc}")
            print()

            # Simple mutation: add instruction
            old_prompt = agent.system_prompt
            mutations_to_add = [
                "\n\n## Special Focus\nСосредоточься на РЕДКИХ и НЕОЧЕВИДНЫХ инсайтах.",
                "\n\n## Quality Metrics\nКаждый инсайт должен быть подкреплен анализом механики.",
                "\n\n## Uniqueness\nНе повторяй стандартные советы - ищи необычные применения.",
                "\n\n## Impact Assessment\nОцени каждый инсайт по трем критериям: практичность, уникальность, применимость.",
                "\n\n## Deep Analysis\nОбъясни ЧТО работает и ПОЧЕМУ это работает на уровне алгоритма ВК.",
            ]

            new_prompt = agent.system_prompt + mutations_to_add[cycle - 1] if cycle <= len(mutations_to_add) else agent.system_prompt
            agent.system_prompt = new_prompt

            print(f"📝 Mutation applied:")
            print(f"   Old length: {len(old_prompt)} chars")
            print(f"   New length: {len(new_prompt)} chars")
            print(f"   Added: {len(new_prompt) - len(old_prompt)} chars")
            print()

            # Test on sample tasks
            print(f"📊 Testing mutated prompt on sample tasks...")
            cycle_task_scores = []

            for i, task in enumerate(tasks[:2], 1):
                trajectory = agent.solve(task)
                feedback = benchmark.evaluate(task, trajectory)
                cycle_task_scores.append(feedback.score)

                status = "↑" if feedback.score > initial_scores[i - 1] else "→"
                change = f"{(feedback.score - initial_scores[i - 1])*100:+.1f}%" if feedback.score != initial_scores[i - 1] else "same"
                print(f"   Task {i}: {feedback.score:.3f} {status} ({change})")

            cycle_avg = sum(cycle_task_scores) / len(cycle_task_scores)
            cycle_scores.append(cycle_avg)

            print(f"\n🎯 Cycle average: {cycle_avg:.3f}")

            if cycle_avg > best_score:
                print(f"✨ NEW BEST! Score improved from {best_score:.3f} → {cycle_avg:.3f} (+{(cycle_avg - best_score)*100:.1f}%)")
                best_score = cycle_avg
                best_prompt = new_prompt
                print(f"✅ Accepting mutation!")
                log_prompt_change(agent, cycle, 1, old_prompt, new_prompt, cycle_avg)
            else:
                print(f"❌ No improvement. Reverting mutation.")
                agent.system_prompt = old_prompt
                log_prompt_change(agent, cycle, 1, old_prompt, new_prompt, cycle_avg)

            print()

        print("\n" + "="*70)
        print("📈 EVOLUTION PROGRESS")
        print("="*70)
        print()

        for i, score in enumerate(cycle_scores):
            bar_length = int(score * 40)
            bar = "█" * bar_length + "░" * (40 - bar_length)
            label = "BASELINE" if i == 0 else f"CYCLE {i}"
            improvement = "" if i == 0 else f" ({(score - cycle_scores[0])*100:+.1f}%)"
            print(f"{label:10} │{bar}│ {score:.3f}{improvement}")

        print()
        print("="*70)
        print("🏆 FINAL RESULTS")
        print("="*70)
        final_score = cycle_scores[-1]
        total_improvement = (final_score - cycle_scores[0]) * 100

        print(f"Baseline score:      {cycle_scores[0]:.3f}")
        print(f"Final score:         {final_score:.3f}")
        print(f"Total improvement:   {total_improvement:+.1f}%")
        print(f"Evolution cycles:    {evolution_cycles}")
        print()

        if total_improvement > 0:
            print("✅ EVOLUTION SUCCESSFUL!")
            print("   Freelancer learned better patterns for VK targeting")
        else:
            print("⚠️  No improvement yet - may need more cycles or different mutations")

        print()
        print("="*70)
        print("📊 FINAL SYSTEM PROMPT (evolved)")
        print("="*70)
        print(best_prompt[:500])
        print("...")
        print()

        print("="*70)
        print("📝 EVOLUTION LOG")
        print("="*70)
        log_file = Path("evolution_log.jsonl")
        if log_file.exists():
            with open(log_file) as f:
                entries = [json.loads(line) for line in f]
            print(f"Total mutations logged: {len(entries)}")
            print(f"Log file: {log_file}")
        print()

        print("💡 NEXT STEPS")
        print("="*70)
        print("  1. Run evolution again to continue improving")
        print("  2. Check evolution_log.jsonl for detailed mutation history")
        print("  3. Review freelancer_workspace/prompts/system.md for evolved prompt")
        print("  4. Commit evolved prompt to git for version control")
        print()
        print(f"✅ Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
