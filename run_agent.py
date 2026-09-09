import argparse

from agents.graph import FinanceAgentGraph
from agents.orchestrator import FinanceWorkflowOrchestrator


def print_help() -> None:
    print("Finance Agent CLI")
    print("Examples:")
    print("  - Evaluate a new investment opportunity")
    print("  - Analyze the latest revenue forecast and recommend action")
    print("  - Review portfolio risk and suggest adjustments")
    print("  - Type 'exit' to quit")
    print("  - Use --source FILE_OR_FOLDER [FILE_OR_FOLDER ...] to analyze other sources")
    print("  - Use --workflow to run the legacy fixed workflow")


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--source", nargs="+")
    parser.add_argument("--workflow", action="store_true")
    args, _ = parser.parse_known_args()
    agent = FinanceAgentGraph()
    workflow = FinanceWorkflowOrchestrator() if args.workflow else None
    print(f"Finance {'workflow orchestrator' if workflow else 'agent'} is ready.\n")
    print_help()
    print()

    while True:
        prompt = input("You: ").strip()
        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        if workflow:
            result = workflow.run_workflow(prompt, args.source)
        else:
            result = agent.run(
                prompt,
                args.source or "data/sample_finance_data.csv",
            )
        print(f"\n{'Workflow' if workflow else 'Agent'} result:\n")
        print(f"Request: {result['request']}")

        if not workflow:
            print(f"Agent status: {result['status']}")
            print(f"Steps used: {result['step_count']}/{result['max_steps']}")
            if result.get("clarification"):
                print(f"Clarification needed: {result['clarification']}")
            elif result.get("response"):
                print(f"Response: {result['response']}")
            elif result.get("approval_required"):
                print(f"Approval required: {result['recommendation']}")
            elif result.get("recommendation"):
                print("Recommendation:")
                print(result["recommendation"])
            if result.get("errors"):
                print(f"Agent errors: {'; '.join(result['errors'])}")
        elif result["route"] == "generic":
            print(f"Response: {result['response']}")
        else:
            dataset = result.get("dataset", {})
            rows = dataset.get("rows")
            file_count = dataset.get("file_count")
            if rows is not None:
                source_label = "file" if file_count == 1 else "files"
                print(f"Analyzed {rows:,} records from {file_count} {source_label}.\n")
            print("Analysis:\n")
            print(result.get("summary", ""))

        print("\n")


if __name__ == "__main__":
    main()
