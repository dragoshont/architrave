#!/usr/bin/env python3
"""Exercise knowledge, coordination and legacy config schema profiles."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    npx = shutil.which('npx')
    if not npx:
        print('test-config-profiles: npx is required', file=sys.stderr)
        return 2
    scratch = ROOT / '.architrave' / 'test-fixtures'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='config-profiles-', dir=scratch) as directory:
        fixture = Path(directory) / 'config.json'

        def expect(name, data, valid):
            fixture.write_text(json.dumps(data), encoding='utf-8')
            result = subprocess.run([npx, '--yes', 'ajv-cli@5', 'validate', '--spec=draft7',
                                     '-s', str(ROOT / 'kit/architrave.config.schema.json'), '-d', str(fixture)],
                                    cwd=ROOT, capture_output=True, text=True)
            if (result.returncode == 0) != valid:
                raise AssertionError(f'{name} should {"pass" if valid else "fail"}\n{result.stdout}{result.stderr}')
            print(f'ok    {name}' + ('' if valid else ' rejected'))

        def example(name):
            return json.loads((ROOT / f'kit/examples/{name}.architrave.json').read_text(encoding='utf-8'))

        knowledge = example('knowledge')
        expect('knowledge-positive', knowledge, True)
        for field in ('build', 'test'):
            missing = copy.deepcopy(knowledge)
            del missing[field]
            expect(f'knowledge-missing-{field}', missing, False)
        expect('knowledge-unknown-kind', dict(knowledge, kind='automation'), False)
        forbidden = {
            'platform': 'web', 'stack': 'other',
            'designSource': {'type': 'design-doc', 'path': 'README.md'},
            'designMap': 'map.json', 'tokens': 'tokens.json', 'tokenBuild': 'echo tokens',
            'knowledgePack': 'web', 'applyTo': ['**'], 'generate': 'echo generate',
            'screenshot': 'echo screenshot', 'backend': {}, 'iac': {}, 'ops': {},
        }
        for field, value in forbidden.items():
            expect(f'knowledge-forbids-{field}', dict(knowledge, **{field: value}), False)
        expect('coordination', example('coordination'), True)
        for name in ('phonodeck', 'sideport', 'tessera'):
            expect(f'legacy-{name}', example(name), True)
        missing = example('sideport')
        del missing['platform']
        expect('legacy-missing-platform', missing, False)
    print('CONFIG-PROFILES: PASS')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError) as exc:
        print(f'FAIL  {exc}', file=sys.stderr)
        raise SystemExit(1)
