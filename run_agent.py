import argparse
from pathlib import Path

from agents.graph import FinanceAgentGraph


def print_help() -> None:
    print("Finance Agent CLI")
    print("Examples:")
    print("  - Evaluate a new investment opportunity")
    print("  - Analyze the latest revenue forecast and recommend action")
    print("  - Review portfolio risk and suggest adjustments")
    print("  - Type 'exit' to quit")
    print("  - Use --source FILE_OR_FOLDER [FILE_OR_FOLDER ...] to analyze other sources")
    print("  - At the prompt, use --source PATH to set the active source")
    print("  - --workflow is a compatibility alias for the bounded agent")


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--source", nargs="+")
    parser.add_argument("--workflow", action="store_true")
    args, _ = parser.parse_known_args()
    agent = FinanceAgentGraph()
    active_source = args.source or "data/sample_finance_data.csv"
    conversation = []
    print("Finance agent is ready.\n")
    if args.workflow:
        print("--workflow is deprecated; using the same bounded agent as the default CLI.\n")
    print_help()
    print()

    while True:
        prompt = input("You: ").strip()
        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        if prompt.lower().startswith("--source"):
            source_text = prompt[len("--source"):].strip().strip('"')
            if not source_text:
                print("Usage: --source PATH_TO_FILE_OR_FOLDER")
                continue
            source_path = Path(source_text)
            if not source_path.exists():
                print(f"Source not found: {source_text}")
                continue
            active_source = source_text
            print(f"Active source set to: {active_source}")
            continue

        result = agent.run(prompt, active_source, conversation=conversation)
        print("\nAgent result:\n")
        print(f"Request: {result['request']}")

        print(f"Agent status: {result['status']}")
        print(f"Steps used: {result['step_count']}/{result['max_steps']}")
        if result.get("clarification"):
            print(f"Clarification needed: {result['clarification']}")
        elif result.get("response"):
            print(f"Response: {result['response']}")
        elif result.get("approval_required"):
            print(f"Approval required: {result['recommendation']}")
        elif result.get("recommendation"):
            loaded = result.get("tool_results", {}).get("load_dataset", {})
            if loaded:
                print(f"Analyzed {loaded.get('rows', 0):,} records from {loaded.get('file_count', 0)} source(s).")
                print(f"Source columns: {', '.join(loaded.get('columns', []))}")
            print("Recommendation:")
            print(result["recommendation"])
        if result.get("errors"):
            print(f"Agent errors: {'; '.join(result['errors'])}")

        assistant_message = (
            result.get("response")
            or result.get("clarification")
            or result.get("recommendation")
            or "; ".join(result.get("errors", []))
        )
        conversation.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": assistant_message},
        ])

        print("\n")


if __name__ == "__main__":
    main()
