"""Client agent: customer profiles and the simulated customer (twin input)."""

# Re-export the main names, so other code can write `from callverse.agents.client import ClientAgent`.
from callverse.agents.client.profiles import CustomerProfile, profile_by_contact_id, sample_profiles
from callverse.agents.client.simulator import ClientAgent, ClientTurn

__all__ = ["ClientAgent", "ClientTurn", "CustomerProfile", "profile_by_contact_id", "sample_profiles"]
