import asyncio
import logging
import time

import pypresence

logger = logging.getLogger(__name__)


class DiscordConnection:
    def __init__(self, factory=pypresence.Presence, clock=time.monotonic):
        self._factory = factory
        self._clock = clock
        self._rpc = None
        self._loop = None
        self._client_id = None
        self._retry_at = 0.0
        self._last_payload = None

    def publish(self, client_id: str, payload: dict | None) -> bool:
        if self._client_id != client_id:
            self.close()
            self._client_id = client_id
            self._retry_at = 0
        if payload is None and self._rpc is None:
            return True
        now = self._clock()
        if now < self._retry_at:
            return False
        try:
            if self._rpc is None:
                self._loop = asyncio.new_event_loop()
                self._rpc = self._factory(
                    client_id, loop=self._loop, connection_timeout=3, response_timeout=3
                )
                self._loop.run_until_complete(asyncio.wait_for(self._rpc.handshake(), timeout=5))
                logger.info("Connected to Discord")
            self._loop.run_until_complete(asyncio.sleep(0))
            if self._rpc.sock_reader is not None and self._rpc.sock_reader.at_eof():
                raise BrokenPipeError("Discord closed the IPC connection")
            if self._equivalent(payload):
                return True
            if payload is None:
                self._rpc.clear()
                logger.info("RPC cleared")
            else:
                arguments = dict(payload)
                arguments["activity_type"] = pypresence.ActivityType(arguments["activity_type"])
                self._rpc.update(**arguments)
                logger.info(
                    "RPC updated: artist=%r; title=%r", payload.get("state"), payload.get("details")
                )
            self._last_payload = payload
            return True
        except Exception as error:
            logger.warning("Discord unavailable (%s); retrying in 5 seconds", type(error).__name__)
            self.close()
            self._retry_at = now + 5
            return False

    def _equivalent(self, payload: dict | None) -> bool:
        previous = self._last_payload
        if payload is None or previous is None:
            return payload is previous
        if {k: v for k, v in payload.items() if k not in ("start", "end")} != {
            k: v for k, v in previous.items() if k not in ("start", "end")
        }:
            return False
        return all(
            (key in payload) == (key in previous)
            and abs(payload.get(key, 0) - previous.get(key, 0)) < 3
            for key in ("start", "end")
        )

    def close(self) -> None:
        rpc, loop = self._rpc, self._loop
        self._rpc = self._loop = self._last_payload = None
        try:
            if rpc is not None and rpc.sock_writer is not None:
                rpc.sock_writer.close()
                if loop is not None and not loop.is_closed():
                    loop.run_until_complete(asyncio.sleep(0))
        except (OSError, RuntimeError):
            logger.debug("Discord pipe already closed")
        finally:
            if loop is not None and not loop.is_closed():
                loop.close()
