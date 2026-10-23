#!/usr/bin/env python3
"""Validate compact legacy and v2 Run fixtures through the Python CLI."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    scratch = ROOT / '.architrave' / 'test-fixtures'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='validate-run-', dir=scratch) as directory:
        def make_repo(name):
            repo = Path(directory) / name
            shutil.copytree(ROOT / 'harness', repo / 'harness',
                            ignore=shutil.ignore_patterns('__pycache__', '*.sh', '*.ps1'))
            return repo

        def command(repo, *args, valid=True):
            result = subprocess.run(args, cwd=repo, capture_output=True, text=True)
            assert (result.returncode == 0) == valid, result.stdout + result.stderr
            return result

        def validate(repo, valid=True):
            command(repo, sys.executable, str(repo / 'harness/architrave_cli.py'),
                    'validate-run', '.architrave/runs/test-run', valid=valid)

        legacy = make_repo('legacy')
        run = legacy / '.architrave/runs/test-run'
        run.mkdir(parents=True)
        summary = {'schema': 'architrave.run.v1', 'runId': 'test-run', 'status': 'in-progress'}
        (run / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
        validate(legacy)
        print('ok    compact legacy run')
        summary['runId'] = ''
        (run / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
        validate(legacy, valid=False)
        print('ok    invalid compact legacy run')

        v2 = make_repo('v2')
        (v2 / 'architrave.config.json').write_text('{}\n', encoding='utf-8')
        for args in (('init', '-q'), ('config', 'user.email', 'architrave@example.invalid'),
                     ('config', 'user.name', 'Architrave Test'), ('add', '.'), ('commit', '-qm', 'fixture')):
            command(v2, 'git', *args)
        command(v2, sys.executable, str(v2 / 'harness/architrave_runtime.py'), 'run',
                '--run-id', 'test-run', '--goal', 'Validate compact Run v2.',
                '--outcome', 'Run files remain valid.')
        validate(v2)
        run = v2 / '.architrave/runs/test-run'
        assert (run / 'recovery.json').is_file(), 'missing recovery.json'
        for name in ('phase-ledger.md', 'summary.json', 'snapshots'):
            assert not (run / name).exists(), f'eager artifact remains: {name}'
        print('ok    compact v2 run')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError) as exc:
        print(f'FAIL  {exc}', file=sys.stderr)
        raise SystemExit(1)
