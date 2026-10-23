#!/usr/bin/env python3
"""Bump the seven synchronized Architrave manifest version fields."""

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    ('plugin.json', ('version',)),
    ('.github/plugin/marketplace.json', ('metadata', 'version')),
    ('.github/plugin/marketplace.json', ('plugins', 0, 'version')),
    ('.claude-plugin/plugin.json', ('version',)),
    ('.claude-plugin/marketplace.json', ('metadata', 'version')),
    ('.claude-plugin/marketplace.json', ('plugins', 0, 'version')),
    ('.codex-plugin/plugin.json', ('version',)),
)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', args[0]):
        print('usage: scripts/bump_version.py <X.Y.Z>   (semver, no leading \'v\')', file=sys.stderr)
        return 1
    version = args[0]
    documents = {}
    try:
        for filename, keys in FIELDS:
            if filename not in documents:
                documents[filename] = json.loads((ROOT / filename).read_text(encoding='utf-8'))
            target = documents[filename]
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = version
        for filename, data in documents.items():
            (ROOT / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print(f'FAIL  version bump: {exc}', file=sys.stderr)
        return 1
    for filename, keys in FIELDS:
        field = ''.join(f'[{key}]' if isinstance(key, int) else f'.{key}' for key in keys)
        print(f'  • {filename} {field} → {version}')
    print(f'\nBumped to {version}. Next:')
    print('  python scripts/check_manifests.py')
    print(f'  git commit -am "Release v{version}" && git tag v{version} && git push origin main --tags')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
