"""In-memory registry of open WebSocket connections.

The socket only pushes events; every message and notification is committed to
PostgreSQL before it is pushed, and clients recover anything they missed over
REST. Because the registry lives in this process's memory, the backend must
run as a single uvicorn worker (see README).
"""
import logging
from fastapi import BackgroundTasks, WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # several tabs per user -> several sockets
        self.connections: dict[int, set[WebSocket]] = {}

    def connect(self, user_id: int, ws: WebSocket) -> None:
        self.connections.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        sockets = self.connections.get(user_id)
        if sockets is None:
            return
        sockets.discard(ws)
        if not sockets:
            del self.connections[user_id]

    def is_connected(self, user_id: int) -> bool:
        return user_id in self.connections

    async def send_to_user(self, user_id: int, event: dict) -> None:
        # offline user: nothing to do, the data is already in the database
        for ws in list(self.connections.get(user_id, ())):
            try:
                await ws.send_json(event)
            except Exception:
                logger.info("dropping dead socket for user %s", user_id)
                self.disconnect(user_id, ws)


manager = ConnectionManager()


def push(background_tasks: BackgroundTasks, user_id: int, event_type: str, data: dict) -> None:
    """Schedule an event for after the response is sent.

    Route handlers are sync and run in a worker thread, so they must not touch
    sockets directly. FastAPI runs async background tasks on the event loop
    after the response, i.e. always after the endpoint's commit.
    """
    background_tasks.add_task(manager.send_to_user, user_id, {"type": event_type, **data})
