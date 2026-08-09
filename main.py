"""CLI entrypoint: ask the agent a question about The Silmarillion."""

import sys

from src.agent.graph_app import ask


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "Who is Beren?"
    result = ask(question)

    print(f"\nRoute: {result.get('route')}")
    print(f"\nAnswer:\n{result.get('answer')}")

    sources = result.get("sources") or []
    if sources:
        print(f"\nSources: {', '.join(sources)}")


if __name__ == "__main__":
    main()
