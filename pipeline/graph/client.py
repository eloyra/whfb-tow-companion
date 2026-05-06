"""
Neo4j driver factory for the graph pipeline.

The driver is a lazy singleton: the first call to ``get_driver()`` reads env vars,
creates the driver, and verifies connectivity.  Subsequent calls return the same
instance.  Call ``close_driver()`` at process exit when running as a long-lived
service; the pipeline CLI shuts down naturally so explicit closing is optional.
"""

from __future__ import annotations

import logging
import os

import neo4j
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

logger = logging.getLogger(__name__)

_driver: neo4j.Driver | None = None


def get_driver() -> neo4j.Driver:
    """Return the singleton Neo4j driver, creating it on first call.

    Reads NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from the environment.
    Raises RuntimeError with an actionable message if connectivity fails.
    """
    global _driver
    if _driver is not None:
        return _driver

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "changeme")

    logger.info("Connecting to Neo4j at %s as %s", uri, user)
    driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
    try:
        _verify(driver)
    except Exception as exc:
        driver.close()
        raise RuntimeError(
            f"Cannot connect to Neo4j at {uri}: {exc}\nRun `make neo4j-up` to start the container."
        ) from exc

    _driver = driver
    logger.info("Neo4j driver ready")
    return _driver


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=10))
def _verify(driver: neo4j.Driver) -> None:
    driver.verify_connectivity()


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
