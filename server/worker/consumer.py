"""Feature worker loop (docs/interfaces.md sections 7 and 8).

Usage::

    .venv/Scripts/python -m server.worker [--env-file .env] [--once]

Reads ``aw:events`` with the consumer group ``features``, turns batches into
encrypted feature windows and acknowledges every entry it has processed.
Only counts are logged, never batch contents.
"""

from __future__ import annotations

from server.common.production import require_production_ready

import argparse
import logging
import os
import sys

import redis

from server.common.config import ConfigError, load_env_file, load_settings
from server.common.redis_keys import EVENTS_STREAM
from server.collector.repository import PostgresRepository
from server.policy.monitor import PolicyMonitor
from server.policy.repository import PgPolicyRepository
from server.session.control import SessionControl
from server.worker.pipeline import FeaturePipeline
from server.worker.scoring import ENROLL_WINDOWS, TrustScorer
from server.worker.scoring_store import PgScoringStore, RedisTrustPublisher
from server.worker.store import PgWindowStore, WindowStore

GROUP = "features"
CONSUMER = "features-1"
BLOCK_MS = 5000

log = logging.getLogger("authwho.worker")


def ensure_group(client: redis.Redis) -> None:
    try:
        client.xgroup_create(EVENTS_STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def run_once(client: redis.Redis, store: WindowStore | None, key: bytes | None,
             block_ms: int | None = None, count: int = 100,
             pipeline: FeaturePipeline | None = None) -> int:
    """Process this consumer's pending entries, then new ones. Returns windows written."""
    if pipeline is None:
        pipeline = FeaturePipeline(store, key)
    ensure_group(client)
    written = 0
    for start, block in (("0", None), (">", block_ms)):
        while True:
            reply = client.xreadgroup(GROUP, CONSUMER, {EVENTS_STREAM: start}, count=count,
                                      block=block)
            raw = reply[0][1] if reply else []
            if not raw:
                break
            entries = [(i, f) for i, f in raw if f]  # trimmed entries come back empty
            written += pipeline.process(entries)
            client.xack(EVENTS_STREAM, GROUP, *[i for i, _ in raw])
            if start == ">":
                break
    return written


def make_client(url: str) -> redis.Redis:
    """Redis client whose read timeout outlasts a blocking XREADGROUP."""
    return redis.Redis.from_url(url, decode_responses=True, socket_timeout=BLOCK_MS / 1000 + 10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn raw event batches into feature windows.")
    parser.add_argument("--env-file", help="read missing variables from this file, for example .env")
    parser.add_argument("--once", action="store_true", help="process what is waiting, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.env_file:
        load_env_file(args.env_file)
    require_production_ready()
    try:
        settings = load_settings()
        key = settings.require("data_key")
        client = make_client(settings.require("redis_url"))
        store = PgWindowStore(settings.require("database_url"))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    enroll = int(os.environ.get("AUTHWHO_ENROLL_WINDOWS", ENROLL_WINDOWS))
    if enroll < 5:
        print("configuration error: AUTHWHO_ENROLL_WINDOWS must be at least 5", file=sys.stderr)
        return 2
    db_url = settings.require("database_url")
    control = SessionControl(client, PostgresRepository(db_url))
    scorer = TrustScorer(PgScoringStore(db_url, key), RedisTrustPublisher(client), enroll_windows=enroll,
                         monitor=PolicyMonitor(PgPolicyRepository(db_url), control), control=control)
    pipeline = FeaturePipeline(store, key, on_window=scorer.on_window)
    try:
        while True:
            written = run_once(client, None, None, block_ms=BLOCK_MS, pipeline=pipeline)
            if written:
                log.info("wrote %d window(s)", written)
            scorer.tick()
            if args.once:
                return 0
    except KeyboardInterrupt:
        return 0
    finally:
        client.close()
