#!/usr/bin/env python3
"""Cross-platform smoke fixtures for the canonical Python gates."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def python_recipe(code):
    argv = [sys.executable, '-c', code]
    return subprocess.list2cmdline(argv) if os.name == 'nt' else shlex.join(argv)


def main():
    scratch = ROOT / '.architrave' / 'test-fixtures'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gates-', dir=scratch) as directory:
        repo = Path(directory)
        for folder, files in (('gates', ('gate_runner.py', 'rubric.md')),
                              ('harness', ('platform_launch.py',))):
            (repo / folder).mkdir()
            for filename in files:
                shutil.copy2(ROOT / folder / filename, repo / folder / filename)
        config_path = repo / 'architrave.config.json'
        knowledge = {
            'kind': 'knowledge',
            'build': python_recipe("from pathlib import Path; Path('build.ran').write_text('build')"),
            'test': python_recipe("from pathlib import Path; Path('test.ran').write_text('test')"),
        }

        def config(value):
            config_path.write_text(json.dumps(value), encoding='utf-8')

        def gate(name, *args, code=0, contains=()):
            result = subprocess.run([sys.executable, str(repo / 'gates/gate_runner.py'), name, *args],
                                    cwd=repo, capture_output=True, text=True)
            if result.returncode != code:
                raise AssertionError(f'{name} expected exit {code}, got {result.returncode}\n{result.stdout}{result.stderr}')
            for text in contains:
                if text not in result.stdout + result.stderr:
                    raise AssertionError(f'{name} missing {text!r}\n{result.stdout}{result.stderr}')
            print(f'ok    {name} {" ".join(args)}')
            return result

        config(knowledge)
        message = 'profile knowledge: UI design JSON validation not applicable'
        gate('checks', '--quick', contains=(message,))
        gate('checks')
        assert (repo / 'build.ran').is_file() and (repo / 'test.ran').is_file(), 'build/test did not execute'
        gate('reconcile', contains=('UI design reconciliation not applicable for knowledge profile',))
        gate('quality-gate', contains=(message, 'knowledge profile config valid'))
        result = gate('quality-gate', '--hook-json')
        assert result.stdout == '{"continue":true}' and result.stderr == '', 'hook success stream contract'
        assert len(result.stdout.encode('utf-8')) == 17, 'hook success bytes'
        config_path.write_text('{', encoding='utf-8')
        result = gate('quality-gate', '--hook-json', code=2, contains=('quality-gate: BLOCKING',))
        assert not result.stdout and 'quality-gate: BLOCKING' in result.stderr, 'hook blocking stream contract'

        (repo / 'strings').mkdir()
        strings = repo / 'strings/en.json'
        config(dict(knowledge, productCopy={'paths': ['strings/*.json']}))
        strings.write_text('{"signIn": "Sign in with Microsoft"}\n', encoding='utf-8')
        gate('checks', '--quick', contains=('ok    product copy (1 files)',))
        strings.write_text('{"status": "Registry only - not certified"}\n', encoding='utf-8')
        gate('checks', '--quick', code=1, contains=("strings/en.json:1: 'Registry only'",))
        gate('quality-gate', code=2)

        legacy = {
            'platform': 'web', 'stack': 'react',
            'designSource': {'type': 'design-doc', 'path': 'README.md'},
            'applyTo': ['src/**'], 'build': python_recipe("print('build-ok')"),
            'test': python_recipe("print('test-ok')"),
        }
        config(legacy)
        gate('checks', '--quick')
        gate('checks')
        gate('quality-gate')
        gate('reconcile')
        gate('backend-checks')
        (repo / 'design.json').write_text('{', encoding='utf-8')
        legacy['designSource']['path'] = 'design.json'
        config(legacy)
        gate('checks', '--quick', code=1)
    print('GATES: PASS')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError) as exc:
        print(f'FAIL  {exc}', file=sys.stderr)
        raise SystemExit(1)
