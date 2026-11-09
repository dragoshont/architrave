#!/usr/bin/env python3
"""Exercise Python content scans, tracked entrypoint policy and fail-closed errors."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def main():
    scratch = ROOT / '.architrave/test-fixtures'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='manifest-scanner-', dir=scratch) as directory:
        repo = Path(directory) / 'repo'
        (repo / 'scripts').mkdir(parents=True)
        scanner = repo / 'scripts/check_manifests.py'
        shutil.copy2(ROOT / 'scripts/check_manifests.py', scanner)
        for args in (('init', '-q'), ('add', 'scripts/check_manifests.py')):
            subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True)
        token = 'mcp-' + 'abcdefghijklmnop'
        for name in ('.architrave/ignored.txt', 'node_modules/ignored.txt', 'assets/ignored.png'):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(token + '\n', encoding='utf-8')

        def scan(code=0, messages=()):
            result = subprocess.run([sys.executable, str(scanner), '--scan-only'], cwd=repo,
                                    capture_output=True, text=True)
            assert result.returncode == code, f'expected {code}, got {result.returncode}\n{result.stdout}{result.stderr}'
            for message in messages:
                assert message in result.stdout + result.stderr, f'missing {message}\n{result.stdout}{result.stderr}'

        scan(messages=('no legacy config references', 'no MCP-looking bearer tokens or auth headers',
                       'no tracked shell entrypoints'))
        print('ok    clean scan excludes runtime, dependencies and images')
        synthetic = repo / 'synthetic-token.txt'
        synthetic.write_text(token + '\n', encoding='utf-8')
        scan(1, ('possible MCP bearer token/auth material committed',))
        synthetic.unlink()
        print('ok    synthetic token rejected')
        legacy = repo / 'legacy-name.txt'
        legacy.write_text('architrave' + '-ui\n', encoding='utf-8')
        scan(1, ('legacy config name references remain',))
        legacy.unlink()
        print('ok    legacy name rejected')

        for name in ('forbidden.ps1', 'forbidden.sh', 'skills/systematic-debugging/forbidden.ps1'):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture\n', encoding='utf-8')
            subprocess.run(['git', 'add', name], cwd=repo, check=True, capture_output=True)
            scan(1, ('tracked shell entrypoints remain', name))
            path.unlink()
        allowed = repo / 'skills/systematic-debugging/find-polluter.sh'
        allowed.write_text('# vendored fixture\n', encoding='utf-8')
        subprocess.run(['git', 'add', str(allowed.relative_to(repo))], cwd=repo, check=True, capture_output=True)
        scan()
        print('ok    tracked shell entrypoints rejected except vendored debugging shell')
        result = subprocess.run([sys.executable, str(scanner), '--unknown'], cwd=repo, capture_output=True)
        assert result.returncode == 2, 'invalid argument must exit 2'
        print('ok    unknown flag rejected')

        bump_spec = importlib.util.spec_from_file_location('bump_version', ROOT / 'scripts/bump_version.py')
        bump = importlib.util.module_from_spec(bump_spec)
        bump_spec.loader.exec_module(bump)
        for version in ('0.0.0', '1.0.2', '12.30.400', '1.0.2-alpha.1', '1.0.2-0'):
            assert bump.VERSION.fullmatch(version), version
        before = (ROOT / 'plugin.json').read_bytes()
        for version in ('01.0.2', '1.00.2', '1.0.02', '1.0.2-01', 'v1.0.2'):
            with contextlib.redirect_stderr(io.StringIO()):
                assert bump.main([version]) == 1, version
        assert (ROOT / 'plugin.json').read_bytes() == before
        print('ok    non-SemVer versions rejected without changing release manifests')

        for filename, _ in bump.FIELDS:
            target = repo / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / filename, target)
        shutil.copy2(ROOT / 'scripts/bump_version.py', repo / 'scripts/bump_version.py')
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'cp1252'
        result = subprocess.run(
            [sys.executable, str(repo / 'scripts/bump_version.py'), '1.0.5'],
            cwd=repo, env=env, capture_output=True, text=True, encoding='cp1252',
        )
        assert result.returncode == 0, f'version bump failed with Windows console encoding: {result.stderr}'
        for filename, keys in bump.FIELDS:
            value = json.loads((repo / filename).read_text(encoding='utf-8'))
            for key in keys:
                value = value[key]
            assert value == '1.0.5', (filename, keys, value)
        print('ok    version bump updates every field with Windows console encoding')

        spec = importlib.util.spec_from_file_location('manifest_scanner_fixture', scanner)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        with mock.patch.object(module, 'scan_repo', side_effect=OSError('synthetic scanner failure')):
            validator = module.Validator()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                validator.repository_scans()
            assert validator.failed
        for message in ('legacy config scan failed', 'MCP bearer/auth scan failed', 'synthetic scanner failure'):
            assert message in output.getvalue(), message
        with mock.patch.object(module.os, 'walk', side_effect=OSError('directory unreadable')):
            try:
                module.scan_repo('anything', repo)
            except OSError:
                pass
            else:
                raise AssertionError('scanner swallowed traversal error')
        with mock.patch.object(Path, 'read_bytes', side_effect=OSError('file unreadable')):
            try:
                module.scan_repo('anything', repo)
            except OSError:
                pass
            else:
                raise AssertionError('scanner swallowed file read error')
        print('ok    scanner operational errors fail closed')
        with mock.patch.object(module.subprocess, 'run', side_effect=OSError('git unavailable')):
            validator = module.Validator()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                validator.python_only()
            assert validator.failed, 'tracked policy silently skipped git failure'
        print('ok    tracked entrypoint lookup errors fail closed')
    print('MANIFEST-SCANNER: PASS')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
        print(f'FAIL  {exc}', file=sys.stderr)
        raise SystemExit(1)
