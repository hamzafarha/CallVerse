"""Script to index contact center documentation into retrieval store."""

import argparse
from pathlib import Path

import yaml
from callverse.agents.advisor import build_knowledge_base, load_knowledge_base_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def order_linked_intents(data_config_path: Path) -> set[str]:
    """The 17 order-linked intents used by the contact generator (configs/data.yaml)."""
    with open(data_config_path, encoding="utf-8") as config_file:
        groups = yaml.safe_load(config_file)["generation"]["contacts"]["intent_groups"]
    return {intent for intents in groups.values() for intent in intents}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs" / "agents.yaml"
    )
    parser.add_argument(
        "--data-config", type=Path, default=PROJECT_ROOT / "configs" / "data.yaml"
    )
    args = parser.parse_args()

    config = load_knowledge_base_config(args.config, PROJECT_ROOT)
    manifest = build_knowledge_base(
        config, allowed_intents=order_linked_intents(args.data_config)
    )
    print(
        f"Indexed {manifest['n_chunks']} chunks from {manifest['n_documents']} "
        f"documents with {manifest['embedding_model']} "
        f"(dim {manifest['dimension']}) into {config.index_dir}"
    )


if __name__ == "__main__":
    main()
