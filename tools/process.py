"""Bounded POSIX subprocess capture shared by execution tools."""

import codecs
import math
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tools.index import ToolResult

DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
DEFAULT_OUTPUT_CHARS = 20000
MAX_OUTPUT_CHARS = 100000

LIMIT_PROPERTIES = {
    "timeout": {
        "type": "number",
        "exclusiveMinimum": 0,
        "maximum": MAX_TIMEOUT,
        "default": DEFAULT_TIMEOUT,
        "description": "Wall-clock seconds, including output capture (maximum 120).",
    },
    "max_output_chars": {
        "type": "integer",
        "minimum": 1,
        "maximum": MAX_OUTPUT_CHARS,
        "default": DEFAULT_OUTPUT_CHARS,
        "description": "Combined stdout/stderr character limit; excess is discarded.",
    },
}


def validate(args, schema):
    try:
        Draft202012Validator(schema).validate(args)
        if not math.isfinite(args.get("timeout", DEFAULT_TIMEOUT)):
            return failure("timeout must be a finite number.")
        return None
    except ValidationError as error:
        return ToolResult(
            status="error", content=f"Invalid arguments: {error.message}", metadata={}
        )


def failure(error, metadata=None):
    return ToolResult(
        status="denied" if isinstance(error, PermissionError) else "error",
        content=str(error),
        metadata=metadata or {},
    )


def run_process(argv, *, cwd, timeout, max_output_chars, env=None):
    metadata = {"cwd": str(Path(cwd).resolve()), "timeout": timeout}
    if os.name != "posix":
        return failure("Execution requires POSIX process-group cleanup.", metadata)
    process = None
    chunks = []
    returned = 0
    truncated = False
    timed_out = False
    decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def capture(data, final=False):
        nonlocal returned, truncated
        text = decoder.decode(data, final=final)
        remaining = max_output_chars - returned
        if len(text) > remaining:
            truncated = True
        text = text[:remaining]
        if text:
            chunks.append(text)
            returned += len(text)

    try:
        deadline = time.monotonic() + timeout
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                for key, _ in selector.select(min(remaining, 0.05)):
                    data = os.read(key.fd, 8192)
                    if data:
                        capture(data)
                    else:
                        selector.unregister(key.fileobj)
                if not selector.get_map() and process.poll() is None:
                    time.sleep(min(remaining, 0.01))
        capture(b"", final=True)
    except (OSError, ValueError) as error:
        return failure(error, metadata)
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            process.stdout.close()
    metadata.update(
        exit_code=process.returncode,
        truncated=truncated,
        returned_chars=returned,
        output_stream="combined",
    )
    return ToolResult(
        status="timeout"
        if timed_out
        else ("success" if process.returncode == 0 else "error"),
        content="".join(chunks),
        metadata=metadata,
    )
