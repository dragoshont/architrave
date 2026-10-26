#!/usr/bin/env python3
"""Validate plugin manifests, repository contracts and cross-platform fixtures.

Usage: python scripts/check_manifests.py [--scan-only]
Python is required; Ruby (YAML) and npx (AJV) retain their existing optional checks.
"""

import argparse
import glob
import json
import os
from pathlib import Path
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
JSON_FILES = (
    'plugin.json',
    '.codex-plugin/plugin.json',
    '.agents/plugins/marketplace.json',
    '.github/plugin/marketplace.json',
    '.claude-plugin/plugin.json',
    '.claude-plugin/marketplace.json',
    'kit/architrave.config.schema.json',
    'kit/examples/knowledge.architrave.json',
    'kit/examples/coordination.architrave.json',
    'kit/examples/phonodeck.architrave.json',
    'kit/examples/sideport.architrave.json',
    'kit/examples/tessera.architrave.json',
    'kit/examples/design-map.stub.json',
    'kit/examples/tokens.web-shadcn.tokens.json',
    'harness/schemas/run-summary.schema.json',
    'harness/schemas/run-v2.schema.json',
    'harness/schemas/event-v2.schema.json',
    'benchmarks/scenarios.schema.json',
    'benchmarks/results.schema.json',
    'benchmarks/scenarios.json',
    'benchmarks/routing-scenarios.json',
    'kit/examples/runtime-v2.architrave.json',
    'benchmarks/fixtures/tessera-shaped/architrave.config.json',
    'benchmarks/fixtures/tessera-shaped/runtime/release-state.json',
    'benchmarks/fixtures/tessera-shaped/deploy/release.json',
    'benchmarks/fixtures/tessera-shaped/deploy/live.json',
)
PYTHON_FILES = (
    'harness/architrave_runtime.py',
    'harness/worker_adapters.py',
    'harness/native_host.py',
    'harness/invariant_engine.py',
    'harness/legibility.py',
    'harness/workspaces.py',
    'harness/validate_run_v2.py',
    'scripts/bench-architrave.py',
    'scripts/judge-bench.py',
    'scripts/summarize-bench.py',
    'scripts/test-benchmark-tools.py',
    'scripts/test-codex-runtime.py',
    'scripts/fixtures/codex_fake.py',
    'scripts/test-runtime-v2.py',
    'scripts/test-worker-adapters.py',
    'scripts/test-invariant-engine.py',
    'scripts/test-legibility.py',
    'scripts/test-workspaces.py',
    'scripts/test-longbuild-runtime.py',
    'scripts/test-benchmark-runtime.py',
    'benchmarks/fixtures/tessera-shaped/server/*.py',
    'benchmarks/fixtures/tessera-shaped/plugin/*.py',
    'benchmarks/fixtures/tessera-shaped/scripts/*.py',
    'benchmarks/fixtures/tessera-shaped/tests/*.py',
)
RUNTIME_TESTS = (
    'scripts/test-runtime-v2.py',
    'scripts/test-worker-adapters.py',
    'scripts/test-native-host.py',
    'scripts/test-opencode-host.py',
    'scripts/test-components.py',
    'scripts/test-improvement.py',
    'scripts/test-native-review.py',
    'scripts/test-quality-cadence.py',
    'scripts/test-ribbon.py',
    'scripts/test-program-board.py',
    'scripts/test-invariant-engine.py',
    'scripts/test-legibility.py',
    'scripts/test-workspaces.py',
    'scripts/test-longbuild-runtime.py',
    'scripts/test-benchmark-runtime.py',
    'scripts/test-platform-launch.py',
    'scripts/test-focus-controls.py',
    'scripts/test-review-launchers.py',
    'scripts/test_install_update.py',
)
EXPECTED_SKILLS = {
    'architrave', 'architrave-agent-authoring', 'architrave-cto',
    'architrave-mcp-integration', 'architrave-review', 'architrave-skill-authoring',
    'architrave-tournament', 'architrave-work', 'skill-creator',
    'subagent-driven-development', 'systematic-debugging',
    'verification-before-completion', 'webapp-testing', 'writing-skills',
}
EXCLUDED_DIRS = {'.git', 'node_modules', '.architrave', '__pycache__'}
EXCLUDED_IMAGES = {'.png', '.jpg', '.jpeg', '.webp'}


def scan_repo(pattern, root=ROOT):
    """Scan bytes in repository files without a platform-specific search tool."""
    compiled = re.compile(pattern.encode('ascii'))
    matches = []

    def onerror(error):
        raise error

    for directory, dirs, files in os.walk(root, onerror=onerror):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix.lower() in EXCLUDED_IMAGES:
                continue
            # Do not follow links outside the repository during content scanning.
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            for number, line in enumerate(path.read_bytes().splitlines(), 1):
                if compiled.search(line):
                    matches.append(f'{path.relative_to(root)}:{number}: {line.decode("utf-8", errors="replace")}')
    return matches


class Validator:
    def __init__(self):
        self.failed = False

    def ok(self, message):
        print(f'  ok    {message}')

    def error(self, message):
        self.failed = True
        print(f'  FAIL  {message}', file=sys.stderr)

    def expect(self, condition, success, failure=None):
        if condition:
            self.ok(success)
        else:
            self.error(failure or success)

    def command(self, message, argv, cwd=ROOT, tail=24):
        try:
            result = subprocess.run([str(arg) for arg in argv], cwd=cwd, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace')
        except OSError as exc:
            self.error(f'{message}: {exc}')
            return False
        if result.returncode == 0:
            self.ok(message)
            return True
        self.error(f'{message} (exit {result.returncode})')
        for line in (result.stdout + result.stderr).splitlines()[-tail:]:
            print(f'      {line}', file=sys.stderr)
        return False

    def python(self, script, *args, message=None, cwd=ROOT):
        return self.command(message or script, [sys.executable, ROOT / script, *args], cwd=cwd)

    def repository_scans(self):
        checks = (
            ('no legacy config name references',
             'ui' + r'kit[.]config|[.]ui' + r'kit[.]json|ui' + r'kit config|architrave' + '-ui',
             'no legacy config references', 'legacy config name references remain', 'legacy config scan failed'),
            ('no MCP bearer/auth material committed',
             r'mcp-[A-Za-z0-9_-]{12,}|Authorization[=:]Bearer\s+mcp-',
             'no MCP-looking bearer tokens or auth headers',
             'possible MCP bearer token/auth material committed', 'MCP bearer/auth scan failed'),
        )
        for heading, pattern, clean, found, failure in checks:
            print(f'== {heading} ==')
            try:
                matches = scan_repo(pattern)
            except OSError as exc:
                self.error(f'{failure}: {exc}')
                continue
            if matches:
                self.error(found)
                for line in matches[:20]:
                    print(f'      {line}', file=sys.stderr)
            else:
                self.ok(clean)

    def python_only(self):
        print('== Python-only tracked entrypoints ==')
        try:
            result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--', '*.ps1', '*.sh'],
                                    cwd=ROOT, capture_output=True, check=True)
            paths = result.stdout.decode('utf-8').split('\0')
            forbidden = [path for path in paths if path and ((ROOT / path).exists() or (ROOT / path).is_symlink()) and
                         (path.endswith('.ps1') or not path.startswith('skills/systematic-debugging/'))]
        except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
            self.error(f'tracked entrypoint scan failed: {exc}')
            return
        self.expect(not forbidden, 'no tracked shell entrypoints',
                    'tracked shell entrypoints remain: ' + ', '.join(forbidden))


def read_json(filename):
    return json.loads((ROOT / filename).read_text(encoding='utf-8'))


def codex_toml_contract():
    # These generated files use only named sections and JSON-compatible strings.
    # Validate that restricted format on Python 3.9/3.10, which lack tomllib.
    def load(path):
        sections = {'': {}}
        current = sections['']
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            section = re.fullmatch(r'\[([A-Za-z_][A-Za-z0-9_.]*)\]', line)
            if section:
                key = section.group(1)
                if key in sections:
                    raise ValueError(f'duplicate TOML section: {key}')
                current = sections[key] = {}
                continue
            assignment = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(".*")', line)
            if not assignment or assignment.group(1) in current:
                raise ValueError(f'invalid generated TOML: {path}: {line}')
            current[assignment.group(1)] = json.loads(assignment.group(2))
        return sections

    config = load(ROOT / '.codex/config.toml')
    assert set(config) == {'', 'agents.architrave_tournament', 'agents.architrave_judge'}
    roles = sorted((ROOT / '.codex/agents').glob('*.toml'))
    assert len(roles) == 2
    for path in roles:
        sections = load(path)
        assert set(sections) == {''}
        data = sections['']
        assert data['sandbox_mode'] == 'read-only'
        assert not ({'model', 'model_reasoning_effort', 'model_provider', 'model_providers',
                     'mcp_servers', 'skills', 'approval_policy'} & data.keys())


def validate_all(validator):
    v = validator
    print('== JSON well-formed ==')
    documents = {}
    for filename in JSON_FILES:
        try:
            documents[filename] = read_json(filename)
            v.ok(filename)
        except (OSError, ValueError) as exc:
            v.error(f'invalid JSON: {filename}: {exc}')

    print('== version in sync (the Claude pin footgun) ==')
    version = documents.get('plugin.json', {}).get('version', 'MISSING')
    v.expect(version != 'MISSING', 'plugin version present', 'plugin.json .version is missing')
    fields = (('.claude-plugin/plugin.json', ('version',)),
              ('.codex-plugin/plugin.json', ('version',)),
              ('.github/plugin/marketplace.json', ('metadata', 'version')),
              ('.github/plugin/marketplace.json', ('plugins', 0, 'version')),
              ('.claude-plugin/marketplace.json', ('metadata', 'version')),
              ('.claude-plugin/marketplace.json', ('plugins', 0, 'version')))
    synchronized = version != 'MISSING'
    for filename, keys in fields:
        try:
            value = documents[filename]
            for key in keys:
                value = value[key]
        except (KeyError, TypeError, IndexError):
            value = 'MISSING'
        if value != version:
            synchronized = False
            v.error(f'version drift: {filename} {keys} = {value} (expected {version})')
    if synchronized:
        v.ok(f'all 7 version fields = {version}')

    print('== name consistency ==')
    for filename in ('plugin.json', '.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
        v.expect(documents.get(filename, {}).get('name') == 'architrave', f'{filename} name = architrave')
    codex = documents.get('.codex-plugin/plugin.json', {})
    v.expect(codex.get('skills') == './skills/' and 'agents' not in codex, 'Codex plugin skills-only contract')
    actual_skills = {path.parent.name for path in (ROOT / 'skills').glob('*/SKILL.md')}
    v.expect(actual_skills == EXPECTED_SKILLS, 'plugin skill inventory (8 Architrave + 6 vendored)',
             f'plugin skill inventory differs: expected {sorted(EXPECTED_SKILLS)}, actual {sorted(actual_skills)}')
    for filename in ('.github/plugin/marketplace.json', '.claude-plugin/marketplace.json'):
        try:
            data = documents[filename]
            valid = data['name'] == data['plugins'][0]['name'] == 'architrave' and data['plugins'][0]['source'] == '.'
        except (KeyError, TypeError, IndexError):
            valid = False
        v.expect(valid, f'{filename} marketplace/plugin names and source')

    npx = shutil.which('npx')
    print('== examples and benchmark scenarios conform to schema (ajv) ==')
    if npx:
        for path in sorted((ROOT / 'kit/examples').glob('*.architrave.json')):
            v.command(f'schema: {path.relative_to(ROOT)}', [npx, '--yes', 'ajv-cli@5', 'validate',
                      '-s', ROOT / 'kit/architrave.config.schema.json', '-d', path])
        for filename in ('benchmarks/scenarios.json', 'benchmarks/routing-scenarios.json'):
            v.command(f'schema: {filename}', [npx, '--yes', 'ajv-cli@5', 'validate',
                      '-s', ROOT / 'benchmarks/scenarios.schema.json', '-d', ROOT / filename])
        v.command('schema: Tessera-shaped fixture config', [npx, '--yes', 'ajv-cli@5', 'validate',
                  '-s', ROOT / 'kit/architrave.config.schema.json',
                  '-d', ROOT / 'benchmarks/fixtures/tessera-shaped/architrave.config.json'])
        print('== generated Run v2 and event schema conformance ==')
        scratch = ROOT / '.architrave/test-fixtures'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='runtime-schema-', dir=scratch) as directory:
            repo = Path(directory)
            (repo / 'README.md').write_text('# schema fixture\n', encoding='utf-8')
            ready = True
            for args in (('init', '-q'), ('config', 'user.email', 'architrave@example.invalid'),
                         ('config', 'user.name', 'Architrave Schema Test'), ('add', 'README.md'),
                         ('commit', '-qm', 'fixture')):
                ready = v.command('schema fixture git ' + args[0], ['git', *args], cwd=repo) and ready
            if ready and v.python('harness/architrave_runtime.py', '--repo', str(repo), 'run',
                                  '--run-id', 'schema-fixture', '--goal', 'Validate schema.',
                                  '--outcome', 'Generated state conforms.'):
                run = repo / '.architrave/runs/schema-fixture'
                v.command('runtime-generated Run conforms to v2 schema', [npx, '--yes', 'ajv-cli@5',
                          'validate', '-s', ROOT / 'harness/schemas/run-v2.schema.json',
                          '-d', run / 'run.json', '--strict=false'])
                try:
                    events = (run / 'events.jsonl').read_text(encoding='utf-8').splitlines()
                    if not events:
                        raise ValueError('no runtime-generated events')
                    for number, event in enumerate(events, 1):
                        fixture = repo / 'event.json'
                        fixture.write_text(json.dumps(json.loads(event)), encoding='utf-8')
                        v.command(f'runtime-generated event {number} conforms to v2 schema',
                                  [npx, '--yes', 'ajv-cli@5', 'validate', '-s',
                                   ROOT / 'harness/schemas/event-v2.schema.json', '-d', fixture, '--strict=false'])
                except (OSError, ValueError) as exc:
                    v.error(f'runtime-generated event schema fixture: {exc}')
    else:
        print('  • npx not found — skipping optional AJV schema checks')
        v.error('Tessera-shaped fixture config schema validation requires npx')
    v.python('scripts/bench-architrave.py', '--validate', '--allow-missing-repos',
             message='available pinned repositories and frozen LongBuild fixtures')
    try:
        baseline = subprocess.run([sys.executable, 'tests/verify.py'],
                                  cwd=ROOT / 'benchmarks/fixtures/tessera-shaped', capture_output=True)
        v.expect(baseline.returncode != 0, 'Tessera-shaped fixture baseline is intentionally unresolved')
    except OSError as exc:
        v.error(f'Tessera-shaped fixture baseline could not execute: {exc}')

    print('== canonical installer path safety ==')
    if (ROOT / 'tools/install_update.py').is_file():
        v.python('tools/install_update.py', '--help', message='canonical Python install/update CLI')
        v.python('scripts/test_install_update.py', message='canonical installer path safety fixtures')
    else:
        v.error('missing canonical tools/install_update.py')
    print('== repository profile fixtures ==')
    for name in ('config-profiles', 'gates', 'manifest-scanner'):
        v.python(f'scripts/test-{name}.py')
    v.repository_scans()
    v.python_only()

    print('== agent/skill frontmatter and skill metadata ==')
    ruby = shutil.which('ruby')
    if ruby:
        frontmatter = (
            'parts=File.read(ARGV[0], encoding: "UTF-8").split("---",3); '
            'abort "no frontmatter" if parts.length < 3; d=YAML.safe_load(parts[1]); '
            '%w[name description].each { |k| abort "missing #{k}" if d[k].to_s.strip.empty? }'
        )
        for pattern in ('agents/*.agent.md', 'skills/*/SKILL.md'):
            for path in sorted(ROOT.glob(pattern)):
                v.command(str(path.relative_to(ROOT)), [ruby, '-ryaml', '-e', frontmatter, path])
        metadata = ('d=YAML.safe_load(File.read(ARGV[0], encoding: "UTF-8")); '
                    'abort "missing interface" unless d["interface"].is_a?(Hash); '
                    'abort "missing policy" unless d["policy"].is_a?(Hash)')
        for path in sorted(ROOT.glob('skills/*/agents/openai.yaml')):
            v.command(str(path.relative_to(ROOT)), [ruby, '-ryaml', '-e', metadata, path])
    else:
        print('  • ruby not found — skipping YAML frontmatter/metadata checks')

    print('== Codex skills and generated roles ==')
    try:
        codex_toml_contract()
        v.ok('Codex registration and two advisory read-only roles')
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
        v.error(f'Codex TOML contract failed: {exc}')
    v.python('scripts/generate-codex-agents.py', '--check', message='generated Codex roles match canonical agents')
    v.expect(not (ROOT / '.agents/skills').exists(), 'no duplicate project skill source')
    for filename in ('test-codex-roles.py', 'test-review-launchers.py', 'test-codex-runtime.py'):
        v.python('scripts/' + filename)

    print('== knowledge packs present ==')
    for name in ('apple', 'microsoft', 'web', 'backend', 'operations-ux', 'design-tokens',
                 'execution-policy', 'learning-loop', 'yagni', 'runtime-v2'):
        path = ROOT / f'knowledge/{name}.md'
        v.expect(path.is_file() and path.stat().st_size > 0, str(path.relative_to(ROOT)))

    print('== Python syntax ==')
    try:
        for pattern in PYTHON_FILES + ('scripts/check_manifests.py', 'scripts/bump_version.py',
                                       'scripts/test-config-profiles.py', 'scripts/test-gates.py',
                                       'scripts/test-manifest-scanner.py', 'scripts/test-validate-run.py'):
            files = glob.glob(str(ROOT / pattern))
            if not files:
                raise ValueError(f'Python source missing: {pattern}')
            for filename in files:
                py_compile.compile(filename, doraise=True)
        v.ok('runtime, benchmark, fixture, and test Python scripts')
    except (OSError, ValueError, py_compile.PyCompileError) as exc:
        v.error(f'Python syntax problem: {exc}')
    v.python('scripts/test-benchmark-tools.py', message='adaptive benchmark fixtures')

    print('== durable Run v2 control-plane fixtures ==')
    for filename in ('test-native-review.mjs', 'test-ribbon.mjs', 'test-session-companion.mjs'):
        v.command(filename, ['node', '--experimental-vm-modules', ROOT / 'scripts' / filename])
    for filename in RUNTIME_TESTS:
        v.python(filename)

    print('== harness and learning validator fixtures ==')
    v.python('scripts/test-validate-run.py')
    v.python('scripts/test-improvement.py', 'ValidationTests', message='learning validator fixtures')
    v.python('scripts/test-improvement.py', 'PromotionTests', message='lesson promotion and picker fixtures')
    v.python('scripts/test-learning-tools.py', message='stale and semantic learning fixtures')
    print('== delivery-focus policy ==')
    v.python('scripts/test-delivery-focus.py', message='delivery-focus rules')
    print(f'PASS — manifests valid, versions in sync ({version})' if not v.failed
          else 'FAIL — fix the FAIL items above', file=sys.stderr if v.failed else sys.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scan-only', action='store_true')
    args = parser.parse_args(argv)
    validator = Validator()
    if args.scan_only:
        validator.repository_scans()
        validator.python_only()
    else:
        validate_all(validator)
    return int(validator.failed)


if __name__ == '__main__':
    raise SystemExit(main())
