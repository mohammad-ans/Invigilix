"""Authoring feature: exam configuration, question bank, enrollment, sandbox and imports.

Layers (NFR05):
    domain/    pure business objects and policies
    ports.py   abstract repositories and services the platform supplies
    services/  application use cases with authorization and transactions
    adapters/  in-memory and SQLAlchemy implementations of the ports
    api/       FastAPI request validation, routes and error mapping
"""
