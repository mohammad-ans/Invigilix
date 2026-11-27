"""Run the 10-minute candidate save and API restart rehearsal on disposable PostgreSQL."""
import json
import multiprocessing
import os
import signal
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from http.client import HTTPConnection
from math import ceil
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from test_api import DeliveryAPI
from backend.app.features.delivery.router import create_router

CANDIDATES = 50
ROUNDS = 120
INTERVAL = 5


def serve(listener, dsn, schema, sessions, ready):
    fixture = DeliveryAPI()
    fixture.dsn, fixture.schema = dsn, schema

    def identity(request: Request):
        account = sessions.get(request.cookies.get("rehearsal"))
        if account is None:
            raise HTTPException(401)
        return account

    @asynccontextmanager
    async def lifespan(_app):
        ready.set()
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(create_router(fixture.connect, identity, fixture.scorer))
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", ws="none"))
    server.run(sockets=[listener])


@contextmanager
def running_api(fixture, sessions):
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        api = ctx.Process(target=serve, args=(listener, fixture.dsn, fixture.schema, sessions, ready))
        api.start()
        try:
            if not ready.wait(15):
                raise RuntimeError("FastAPI failed to start")
            yield listener.getsockname()[1]
        finally:
            if api.is_alive():
                os.kill(api.pid, signal.SIGTERM)
            api.join(10)
            if api.is_alive():
                api.kill()
                api.join()


def request(port, token, method, path, body=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=12)
    try:
        conn.request(method, path, json.dumps(body) if body is not None else None,
                     {"Cookie": "rehearsal=" + token, "Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError(f"{method} received HTTP {response.status}")
        return json.loads(response.read())
    finally:
        conn.close()


def rehearse(fixture):
    sessions = {uuid4().hex: uuid4() for _ in range(CANDIDATES)}
    with fixture.connect() as db:
        db.execute("""UPDATE exam SET opens_at=now()-interval '1 hour', closes_at=now()+interval '2 hours',
                      published_at=now()-interval '1 day'""")
        for account in sessions.values():
            db.execute("INSERT INTO account(id,email,display_name,password_hash) VALUES (%s,%s,'Test','fake')",
                       (account, str(account)))
            db.execute("INSERT INTO account_role VALUES (%s,'candidate')", (account,))
            db.execute("INSERT INTO enrollment VALUES (%s,%s,%s,true)", (fixture.exam, account, fixture.other))

    latencies = []
    with ThreadPoolExecutor(CANDIDATES) as clients:
        with running_api(fixture, sessions) as port:
            def enter(token):
                paper = request(port, token, "POST", fixture.enter_path)
                return token, "/attempts/" + paper["attempt_id"]

            attempts = list(clients.map(enter, sessions))
            start = time.monotonic()
            for revision in range(1, ROUNDS + 1):
                time.sleep(max(0, start + INTERVAL * revision - time.monotonic()))

                def save(attempt):
                    token, path = attempt
                    started = time.monotonic()
                    ack = request(port, token, "PUT", path + "/items/3",
                                  {"base_revision": revision - 1, "written_answer": str(revision), "flagged": False})
                    elapsed = time.monotonic() - started
                    if ack["revision"] != revision:
                        raise AssertionError("Unexpected acknowledged revision")
                    return elapsed

                latencies.extend(clients.map(save, attempts))
                if revision % 20 == 0:
                    print(f"{len(latencies)} acknowledged", flush=True)
            duration = time.monotonic() - start
        with running_api(fixture, sessions) as port:
            def verify(attempt):
                token, path = attempt
                paper = request(port, token, "GET", path)
                item = next(i for i in paper["items"] if i["slot"] == 3)
                if (item["revision"], item["written_answer"]) != (ROUNDS, str(ROUNDS)):
                    raise AssertionError("An acknowledged answer did not survive the API restart")

            list(clients.map(verify, attempts))
    p95 = sorted(latencies)[ceil(0.95 * len(latencies)) - 1]
    print(f"{CANDIDATES} candidates, {len(latencies)} acknowledged saves, {duration:.1f} s, "
          f"p95 {p95 * 1000:.1f} ms, {len(attempts)} final answers restored after process restart")
    if p95 > 2:
        raise AssertionError("Save latency exceeds the two-second SRS target")


if __name__ == "__main__":
    if not os.getenv("DELIVERY_TEST_DSN"):
        raise SystemExit("Set DELIVERY_TEST_DSN to a disposable PostgreSQL database")
    case = DeliveryAPI()
    try:
        case.setUp()
        case.clock.stop()
        rehearse(case)
    finally:
        case.doCleanups()
