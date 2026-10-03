"""Offer sources.

Every source module exposes:

    fetch(search_term) -> list[dict]

returning offers in the canonical shape defined by normalize.normalize_offer().
Adding a source means adding a module here, not touching the store or the CLI.
"""
