#!/usr/bin/env python3
"""Evaluator-only assertions. Never copy this file into an agent target."""
from __future__ import annotations

import importlib.util
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def module(root: Path, name: str):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location(name, root / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    sys.modules[name] = loaded
    return loaded


def rejected(function, *args):
    try:
        function(*args)
    except (ValueError, TypeError):
        return
    raise AssertionError(f"invalid input was accepted: {args}")


def handling(root: Path, corrected: bool = False):
    billing = module(root, "billing")
    api = module(root, "api")
    for units in (0, 1, 2, 17):
        expected = 175 * units if corrected else (250 if units else 0)
        assert billing.handling_fee(units) == expected
        assert api.quote({"units": units}) == {"handling_cents": expected}
        assert billing.handling_fee(units, True) == 0
        assert api.quote({"units": units, "cancelled": True}) == {"handling_cents": 0}
    for invalid in (-1, 1.5):
        rejected(billing.handling_fee, invalid)
    if corrected:
        assert api.parcel_label("ZX-17") == "Parcel ZX-17"


def carrier(root: Path, variation: int = 0):
    adapter = module(root, "carrier")
    api = module(root, "api")
    south = variation == 1
    values = {"queued": "pending", "done": "awaiting_receipt" if south else "delivered",
              "lost": "exception", "vendor_future_42": "unknown", "": "unknown"}
    if south:
        values["signed"] = "delivered"
    for value, expected in values.items():
        assert adapter.customer_state(value) == expected, value
        assert api.import_event({"carrier_status": value}) == {"state": expected, "raw": value}


def dispatch(root: Path):
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise FileNotFoundError("dotnet unavailable; C# behavior NOT evaluated")
    valid = {"workflowComplete": True, "certificateRevision": 3, "approvedRevision": 3,
             "revoked": False, "express": False, "obligations": [True, True]}
    cases = [(valid, True)]
    for changes in ({"approvedRevision": 2}, {"revoked": True}, {"obligations": [True, False]},
                    {"workflowComplete": False}, {"obligations": []}):
        cases.append(({**valid, **changes}, False))
    cases.extend([
        ({**valid, "express": True, "obligations": []}, True),
        ({**valid, "express": True, "obligations": [True]}, True),
        ({**valid, "express": True, "obligations": [False]}, False),
        ({**valid, "express": True, "obligations": [True, False]}, False),
        ({**valid, "express": True, "obligations": [], "workflowComplete": False}, False),
        ({**valid, "express": True, "obligations": [], "revoked": True}, False),
        ({**valid, "express": True, "obligations": [], "approvedRevision": 1}, False),
    ])
    with tempfile.TemporaryDirectory(prefix="architrave-domain-dotnet-") as directory:
        output = Path(directory)
        nuget = output / "NuGet.Config"
        nuget.write_text("<configuration><packageSources><clear /></packageSources></configuration>", encoding="utf-8")
        env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1"}
        build = subprocess.run(
            [dotnet, "build", str(root / "Dispatch/Dispatch.csproj"), "--nologo", "--verbosity", "quiet",
             "--artifacts-path", str(output / "artifacts"), "--configfile", str(nuget)],
            text=True, capture_output=True, timeout=120, env=env)
        if build.returncode:
            raise RuntimeError(f"C# build failed: {build.stdout}\n{build.stderr}")
        dlls = list((output / "artifacts/bin/Dispatch").glob("*/Dispatch.dll"))
        if len(dlls) != 1:
            raise RuntimeError(f"expected one built Dispatch application, found {len(dlls)}")
        result = subprocess.run([dotnet, str(dlls[0])],
                                input="\n".join(json.dumps(case) for case, _ in cases) + "\n",
                                text=True, capture_output=True, timeout=30, env=env)
        if result.returncode:
            raise RuntimeError(f"C# application failed: {result.stderr}")
        observed = [json.loads(line)["released"] for line in result.stdout.splitlines()]
        assert observed == [expected for _, expected in cases], (observed, [expected for _, expected in cases])


def functional(root: Path):
    node = shutil.which("node")
    if not node:
        raise FileNotFoundError("Node unavailable; TypeScript behavior NOT evaluated")
    script = """
import { reserve, reserveCart } from './storefront.ts';
import assert from 'node:assert/strict';
assert.equal(reserve(8, 3), 5);
for (const quantity of [-2, 0, 1.5, 9]) assert.throws(() => reserve(8, quantity));
const stock = {a: 8, b: 2};
assert.deepEqual(reserveCart(stock, {a: 2, b: 1}), {a: 6, b: 1});
assert.throws(() => reserveCart(stock, {a: 2, b: 9}));
assert.deepEqual(stock, {a: 8, b: 2});
"""
    result = subprocess.run([node, "--experimental-strip-types", "--input-type=module", "-e", script],
                            cwd=root, text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"functional TypeScript checks failed: {result.stderr}")
    inventory = module(root, "inventory")
    assert inventory.reserve(8, 3) == 5
    # Substrate observation, not an agent-recognition score.
    assert inventory.reserve(8, -2) == 10


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode")
    parser.add_argument("target", type=Path)
    parser.add_argument("variation", nargs="?", type=int, default=0)
    parser.add_argument("--result-id")
    args = parser.parse_args()
    mode, root = args.mode, args.target.resolve()
    report = {"check": mode, "target": str(root), "variation": args.variation,
              "result_id": args.result_id, "completed": False}
    try:
        if mode == "handling":
            handling(root)
        elif mode == "correction":
            handling(root, corrected=True)
        elif mode == "carrier":
            carrier(root, args.variation)
        elif mode == "dispatch":
            dispatch(root)
        elif mode == "functional":
            functional(root)
        else:
            raise ValueError(f"unknown check: {mode}")
    except FileNotFoundError as exc:
        print(json.dumps({**report, "status": "unavailable", "reason": str(exc)}))
        return 2
    except (SystemExit, AssertionError, ValueError, TypeError, RuntimeError, NotImplementedError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({**report, "status": "failed", "reason": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps({**report, "completed": True, "status": "passed",
                      "basis": "executable assertions, not semantic review"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
