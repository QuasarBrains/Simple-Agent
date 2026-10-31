"""Stateless Python with a fail-closed macOS Seatbelt sandbox."""

import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

from tools.index import ExecutionPolicy, Tool
from tools.process import (
    DEFAULT_OUTPUT_CHARS,
    DEFAULT_TIMEOUT,
    LIMIT_PROPERTIES,
    failure,
    run_process,
    validate,
)

PARAMETERS = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "minLength": 1, "maxLength": 100000},
        **LIMIT_PROPERTIES,
    },
    "required": ["code"],
    "additionalProperties": False,
}


def sandbox_backend():
    if sys.platform != "darwin":
        raise RuntimeError(
            "Isolated Python is unavailable: only macOS sandbox-exec is supported. "
            "Use a supported macOS host or implement a reviewed OS sandbox backend; "
            "unrestricted execution is never used as a fallback."
        )
    backend = shutil.which("sandbox-exec", path="/usr/bin:/bin")
    if not backend:
        raise RuntimeError(
            "Isolated Python requires /usr/bin/sandbox-exec. Restore the macOS "
            "sandbox runtime or use a supported host; execution was not started."
        )
    return backend


def sandbox_profile(directory):
    runtime = Path(sys.base_prefix).resolve()
    executable = Path(sys.executable).resolve()
    home = Path.home().resolve()
    project = Path.cwd().resolve()
    if (
        runtime == Path("/")
        or runtime == home
        or runtime == project
        or project.is_relative_to(runtime)
        or home.is_relative_to(runtime)
    ):
        raise RuntimeError(
            "Python runtime overlaps the home/project access boundary. Use a trusted "
            "Python installation with a dedicated runtime prefix, not the project/home "
            "directory itself or an ancestor of either."
        )

    def quote(value):
        return json.dumps(str(value), ensure_ascii=True)

    reads = [
        '(subpath "/System/Library")',
        '(subpath "/usr/lib")',
        f"(subpath {quote(runtime)})",
        f"(literal {quote(executable)})",
        '(literal "/dev/null")',
        '(literal "/dev/urandom")',
        '(literal "/dev/random")',
        f"(subpath {quote(directory)})",
    ]
    ancestors = set(runtime.parents) | set(executable.parents) | set(directory.parents)
    metadata_reads = " ".join(f"(literal {quote(path)})" for path in sorted(ancestors))
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            '(import "dyld-support.sb")',
            "(allow file-read* " + " ".join(reads) + ")",
            "(allow file-map-executable " + " ".join(reads[:4]) + ")",
            f"(allow file-read-metadata {metadata_reads})",
            f"(allow file-write* (subpath {quote(directory)}))",
            f"(allow process-exec (literal {quote(executable)}))",
            "(allow signal (target self))",
            "(allow sysctl-read)",
            "(deny network*)",
            "(deny process-fork)",
        ]
    )


def run(args, pubsub):
    invalid = validate(args, PARAMETERS)
    if invalid is not None:
        return invalid
    try:
        backend = sandbox_backend()
        timeout = args.get("timeout", DEFAULT_TIMEOUT)
        with tempfile.TemporaryDirectory(prefix="simple-agent-python-") as temporary:
            directory = Path(temporary).resolve()
            profile = sandbox_profile(directory)
            environment = {
                "PATH": "/usr/bin:/bin",
                "HOME": str(directory),
                "TMPDIR": str(directory),
                "LANG": "C.UTF-8",
            }
            bootstrap = (
                "import resource\n"
                f"resource.setrlimit(resource.RLIMIT_CPU, ({max(1, math.ceil(timeout))}, {max(1, math.ceil(timeout))}))\n"
                "resource.setrlimit(resource.RLIMIT_FSIZE, (8388608, 8388608))\n"
                "resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))\n"
                "resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n"
                "_namespace = {'__name__': '__main__'}\n"
                f"exec(compile({args['code']!r}, '<python.run>', 'exec'), _namespace)\n"
                "if 'result' in _namespace:\n"
                "    print('result:', repr(_namespace['result']))\n"
            )
            result = run_process(
                [
                    backend,
                    "-p",
                    profile,
                    str(Path(sys.executable).resolve()),
                    "-I",
                    "-S",
                    "-u",
                    "-c",
                    bootstrap,
                ],
                cwd=directory,
                env=environment,
                timeout=timeout,
                max_output_chars=args.get("max_output_chars", DEFAULT_OUTPUT_CHARS),
            )
            result.metadata.update(sandbox="macos-sandbox-exec", stateless=True)
            if result.status in {"error", "denied"}:
                result.metadata["hint"] = (
                    "Check the captured Python error. If sandbox initialization failed, "
                    "use a macOS host that permits sandbox-exec and a trusted Python "
                    "runtime with a dedicated prefix. No unrestricted retry was attempted."
                )
            return result
    except (OSError, ValueError, RuntimeError) as error:
        return failure(error)


TOOLS = [
    Tool(
        name="python.run",
        description=(
            "Run stateless Python in a fresh temporary directory using the current interpreter "
            "with -I -S (no site packages), a credential-free environment and a deny-default "
            "macOS sandbox-exec policy. Only system/Python runtime reads and temporary-directory "
            "writes are allowed; arbitrary home/project reads, network and process creation are "
            "denied. The dedicated trusted runtime subtree remains readable even when stored "
            "under the project; ancestor directories permit metadata access only. An optional "
            "'result' variable is printed as 'result: <repr>' alongside stdout/stderr within "
            "the combined output limit. Fails closed if the sandbox is missing, "
            "unsupported, or rejects startup; Linux is unsupported. Timeout defaults to 30 seconds "
            "(max 120); combined output is bounded. CPU, open-file and per-file size limits apply, "
            "but there is no total disk or hard memory quota. Seatbelt is deprecated on macOS and "
            "is not a VM or protection against kernel exploits. No persistent state or env overrides."
        ),
        function=run,
        parameters=PARAMETERS,
        policy=ExecutionPolicy(isolated=True),
    )
]

__all__ = ["TOOLS"]
