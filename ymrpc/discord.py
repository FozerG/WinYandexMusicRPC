import asyncio
import json
import logging
import struct
import time

import pypresence
from pypresence.exceptions import DiscordError, DiscordNotFound, InvalidPipe
from pypresence.utils import get_ipc_path

logger = logging.getLogger(__name__)


class ProfilePresence(pypresence.Presence):
    """Retain the public profile from the local IPC READY handshake."""

    async def handshake(self):
        path = get_ipc_path(self.pipe)
        if not path:
            raise DiscordNotFound
        await self.create_reader_writer(path)
        self.send_data(0, {"v": 1, "client_id": self.client_id})
        opcode, size = struct.unpack("<ii", await self.sock_reader.readexactly(8))
        if size < 0 or size > 1_000_000:
            raise InvalidPipe
        response = json.loads(await self.sock_reader.readexactly(size))
        if opcode == 2 or "code" in response:
            raise DiscordError(response.get("code", 0), response.get("message", "IPC closed"))
        if response.get("evt") != "READY":
            raise InvalidPipe
        user = response.get("data", {}).get("user") or {}
        self.user = {key: user.get(key) for key in ("id", "username", "global_name", "avatar")}


class DiscordConnection:
    def __init__(self, factory=ProfilePresence, clock=time.monotonic, profile_changed=None):
        self._factory = factory
        self._clock = clock
        self._rpc = None
        self._loop = None
        self._client_id = None
        self._retry_at = 0.0
        self._last_payload = None
        self._profile_changed = profile_changed or (lambda value: None)

    def publish(self, client_id: str, payload: dict | None) -> bool:
        if self._client_id != client_id:
            self.close()
            self._client_id = client_id
            self._retry_at = 0
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
                self._profile_changed({"connected": True, **getattr(self._rpc, "user", {})})
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
        self._profile_changed({"connected": False})
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
