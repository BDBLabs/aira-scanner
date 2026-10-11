"""Portable repository verification implemented with Dagger.

Scoped to this repository's authoritative gate, which is
`.github/workflows/ci.yml`: it runs from `working-directory: CLI`, installs
`.[dev]` from there, and runs `pytest tests/ -v`.

An earlier version of this lattice ran everything from the repository root.
That silently verified nothing: the root `pyproject.toml` declares only
`pyyaml` and no `dev` extra, so `pip install -e ".[dev]"` fails and the
fallback installs a package with none of the scanner's real dependencies
(`tree-sitter` and its three language grammars). `pytest -q` then still
*collects* 117 tests by walking into `CLI/`, but 14 of 19 test files import
`aira` or `tree_sitter`, so they error on import. The job would be red for
the wrong reason — a missing install, not a code defect.

The Dagger container therefore `cd /src/CLI` first, which is exactly what
the real CI's `working-directory` does.
"""

from __future__ import annotations

from typing import Annotated

import dagger
from dagger import DefaultPath, dag, function, object_type

PYTHON_IMAGE = "python:3.12-slim"
NODE_IMAGE = "node:20-bookworm-slim"
GITLEAKS_IMAGE = (
    "ghcr.io/gitleaks/gitleaks:v8.28.0@sha256:"
    "cdbb7c955abce02001a9f6c9f602fb195b7fadc1e812065883f695d1eeaba854"
)
SOURCE = Annotated[dagger.Directory, DefaultPath("/")]

# The real CI's only Python job. Kept verbatim so shadow mode cannot drift
# into asserting something the authoritative gate does not.
REAL_CI_STEPS = [
    'pip install -e ".[dev]"',
    "pytest tests/ -v",
]


@object_type
class RepoCi:
    def _container(self, image: str, source: dagger.Directory, workdir: str = "/src/CLI") -> dagger.Container:
        return dag.container().from_(image).with_directory("/src", source).with_workdir(workdir)

    @function
    async def node(self, source: SOURCE) -> str:
        # This repository has no root/npm project (package.json at root is a
        # stub, and lib/ is plain JS with no manifest), so Node verification is
        # a no-op. Kept for parity with the portable-CI pattern.
        return "node: skipped (no root package.json project)"

    @function
    async def python(self, source: SOURCE) -> str:
        # Mirrors .github/workflows/ci.yml: working-directory CLI, install
        # -e .[dev], then pytest tests/ -v. Adding a coverage gate here that
        # the real CI does not have would make shadow mode *stricter* than
        # authoritative, which is the wrong direction to drift.
        steps = "\n".join(REAL_CI_STEPS)
        script = f"""set -eu
cd /src/CLI
{steps}
"""
        await self._container(PYTHON_IMAGE, source).with_exec(["sh", "-lc", script]).stdout()
        return "python: passed"

    @function
    async def production_image(self, source: SOURCE) -> str:
        # No root Dockerfile in this repository (there is none at the root of
        # main), so this leg is genuinely not applicable rather than skipped.
        return "production-image: skipped (no root Dockerfile)"

    @function
    async def secrets(self, source: SOURCE) -> str:
        ctr = (
            dag.container()
            .from_(GITLEAKS_IMAGE)
            .with_directory("/src", source)
            .with_workdir("/src")
            .with_exec(["sh", "-lc", "test -d .git || { echo '.git history is required'; exit 42; }"])
            .with_exec(["gitleaks", "detect", "--redact", "-v", "--source", "."])
        )
        await ctr.stdout()
        return "secrets: passed"

    @function
    async def verify(self, source: SOURCE) -> str:
        return "\n".join(
            [
                await self.node(source),
                await self.python(source),
                await self.production_image(source),
                await self.secrets(source),
            ]
        )
