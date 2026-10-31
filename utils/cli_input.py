import asyncio
from collections import deque
from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import Event, Lock, current_thread, main_thread
from typing import Callable

from prompt_toolkit.patch_stdout import patch_stdout

from utils.terminal import terminal


@dataclass(eq=False)
class _Approval:
    tool: object
    arguments: dict
    done: Event = field(default_factory=Event)
    approved: bool = False


@dataclass
class _UserInput:
    mode: str
    initial: bool
    generation: int


class CLIInput:
    """Queue terminal input for the main thread and release approvals on shutdown."""

    def __init__(
        self,
        output=terminal,
        waiting: Callable[[str], bool] | None = None,
        on_close: Callable[[], None] | None = None,
    ):
        self.output = output
        self.waiting = waiting
        self.on_close = on_close
        self._queue = Queue()
        self._lock = Lock()
        self._closed = Event()
        self._approvals: set[_Approval] = set()
        self._generation = 0

    def submit_user(self, mode: str, *, initial: bool = False):
        if mode not in ("user", "stimulus"):
            raise ValueError(f"Unknown input mode: {mode}")
        with self._lock:
            if not self._closed.is_set():
                self._queue.put(_UserInput(mode, initial, self._generation))

    def cancel_user(self):
        with self._lock:
            self._generation += 1

    def approve(self, tool, arguments: dict) -> bool:
        if current_thread() is main_thread():
            raise RuntimeError("Approval requests must come from a worker thread")
        request = _Approval(tool, arguments)
        with self._lock:
            if self._closed.is_set():
                return False
            self._approvals.add(request)
            self._queue.put(request)
        try:
            request.done.wait()
            return request.approved
        finally:
            with self._lock:
                self._approvals.discard(request)

    def _current(self, request: _UserInput) -> bool:
        if request.initial:
            return True
        with self._lock:
            current = request.generation == self._generation
        return current and (self.waiting is None or self.waiting(request.mode))

    def run(self, running: Callable[[], bool], user: Callable[[str], None]):
        if current_thread() is not main_thread():
            raise RuntimeError("CLI input must run on the main thread")
        try:
            with patch_stdout(raw=True):
                asyncio.run(self._run(running, user))
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            self.close()

    async def _run(self, running: Callable[[], bool], user: Callable[[str], None]):
        users = deque()
        approvals = deque()
        active = None
        request = None

        def complete(current, value):
            if self._closed.is_set() or not running():
                return
            if isinstance(current, _Approval):
                with self._lock:
                    current.approved = bool(value) and not self._closed.is_set()
                    current.done.set()
            elif value.strip():
                user(value)
            elif self._current(current):
                users.append(current)

        try:
            while not self._closed.is_set() and running():
                while True:
                    try:
                        queued = self._queue.get_nowait()
                    except Empty:
                        break
                    if isinstance(queued, _Approval):
                        approvals.append(queued)
                    elif isinstance(queued, _UserInput):
                        users.append(queued)

                if active is not None:
                    if active.done():
                        complete(request, active.result())
                        active = None
                        request = None
                        continue
                    if isinstance(request, _UserInput) and (
                        approvals or not self._current(request)
                    ):
                        active.cancel()
                        try:
                            value = await active
                        except asyncio.CancelledError:
                            if self._current(request):
                                users.appendleft(request)
                        else:
                            complete(request, value)
                        active = None
                        request = None
                        continue

                if active is None:
                    if approvals:
                        request = approvals.popleft()
                        active = asyncio.create_task(
                            self.output.approve_tool_async(
                                request.tool, request.arguments
                            )
                        )
                    else:
                        while users:
                            request = users.popleft()
                            if self._current(request):
                                active = asyncio.create_task(
                                    self.output.prompt_async(
                                        reply=request.mode == "user"
                                    )
                                )
                                break

                if active is None:
                    await asyncio.sleep(0.05)
                else:
                    await asyncio.wait({active}, timeout=0.05)
        finally:
            self.close()
            if active is not None:
                active.cancel()
                await asyncio.gather(active, return_exceptions=True)

    def close(self):
        with self._lock:
            if self._closed.is_set():
                return
            if self.on_close is not None:
                self.on_close()
            self._closed.set()
            for request in self._approvals:
                request.approved = False
                request.done.set()
            self._queue.put(None)
