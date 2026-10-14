"""Generate tickets and chat logs, then build the SQLite store (Phase 1F)."""

import argparse
from pathlib import Path

import pandas as pd
import yaml
from callverse.data import (
    ORDER_COLUMNS,
    build_database,
    generate_chat_messages,
    generate_tickets,
    load_ticket_config,
)
from callverse.simulation import load_simulation_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-config", type=Path, default=PROJECT_ROOT / "configs" / "data.yaml"
    )
    parser.add_argument(
        "--simulation-config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "simulation.yaml",
    )
    args = parser.parse_args()

    ticket_config = load_ticket_config(args.data_config)
    with open(args.data_config, encoding="utf-8") as config_file:
        db_path = PROJECT_ROOT / yaml.safe_load(config_file)["database"]["path"]
    simulation = load_simulation_config(args.simulation_config)
    service_times = {
        group: (spec.mean_seconds, spec.cv)
        for group, spec in simulation.service_times.items()
    }

    def read(name: str) -> pd.DataFrame:
        return pd.read_parquet(PROCESSED_DIR / f"{name}.parquet")

    contacts = read("synthetic_contacts")
    orders = read("olist_orders_analytical")

    tickets = generate_tickets(contacts, orders, ticket_config, service_times)
    messages = generate_chat_messages(
        tickets, contacts, orders, ticket_config.random_seed
    )
    tickets.to_parquet(PROCESSED_DIR / "synthetic_tickets.parquet", index=False)
    messages.to_parquet(PROCESSED_DIR / "synthetic_chat_messages.parquet", index=False)
    print(f"{len(tickets)} tickets and {len(messages)} chat messages written.")

    # generator_* columns hold the hidden cause of each contact: kept in Parquet for
    # evaluation, never exposed in the store that agents query.
    contact_columns = [c for c in contacts.columns if not c.startswith("generator_")]
    counts = build_database(
        {
            "customers": read("olist_customers_prepared"),
            "sellers": read("olist_sellers_prepared"),
            "products": read("olist_products_prepared"),
            "orders": orders[ORDER_COLUMNS],
            "order_items": read("olist_order_items_prepared"),
            "payments": read("olist_payments_prepared"),
            "contacts": contacts[contact_columns],
            "tickets": tickets,
            "chat_messages": messages,
        },
        db_path,
    )
    size_mb = db_path.stat().st_size / 1e6
    print(f"SQLite store {db_path} ({size_mb:.0f} MB):")
    for table, rows in counts.items():
        print(f"  {table:<14}{rows:>9,}")


if __name__ == "__main__":
    main()
