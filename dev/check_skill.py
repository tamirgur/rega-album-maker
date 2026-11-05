#!/usr/bin/env python3
"""Check the skill against the Agent Skills specification and this repo's own rules. No network, no browser.

    python dev/check_skill.py

Spec (agentskills.io/specification and Anthropic's skill authoring guide):
- name: 1-64 characters, a-z 0-9 and single hyphens, not starting or ending with one, the folder's name, no
  reserved words (anthropic, claude);
- description: 1-1024 characters, no XML tags; compatibility: at most 500 characters; metadata: string values;
- SKILL.md body under 500 lines; reference files over 100 lines open with a table of contents; references one level
  deep from SKILL.md; forward slashes in paths.
Repo rules: one version everywhere (plugin.json, SKILL.md metadata, CHANGELOG.md); every file SKILL.md names exists;
every font, palette and illustration a style uses exists; every script compiles.
"""
import json
import os
import py_compile
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, 'skills', 'rega-album-maker')
errors = []


def err(msg):
    errors.append(msg)


def frontmatter(text):
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', text, re.S)
    if not m:
        err('SKILL.md has no YAML frontmatter')
        return {}, text
    fm, body, key = {}, m.group(2), None
    for line in m.group(1).split('\n'):
        if re.match(r'^\s+\S', line) and key:          # a nested key, under metadata
            k, _, v = line.strip().partition(':')
            fm.setdefault(key, {})[k.strip()] = v.strip().strip('"')
            continue
        k, _, v = line.partition(':')
        key = k.strip()
        fm[key] = v.strip() if v.strip() else {}
    return fm, body


text = open(os.path.join(SKILL, 'SKILL.md'), encoding='utf-8').read()
fm, body = frontmatter(text)
name, desc = fm.get('name', ''), fm.get('description', '')
if not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', name) or len(name) > 64:
    err(f'name "{name}": 1-64 characters of a-z, 0-9 and single hyphens')
if name != os.path.basename(SKILL):
    err(f'name "{name}" must match the folder "{os.path.basename(SKILL)}"')
if re.search(r'anthropic|claude', name):
    err('name must not contain the reserved words anthropic or claude')
if not 1 <= len(desc) <= 1024 or re.search(r'<[a-zA-Z/]', desc):
    err(f'description: 1-1024 characters without XML tags (now {len(desc)})')
if len(fm.get('compatibility', '')) > 500:
    err('compatibility: at most 500 characters')
if not isinstance(fm.get('metadata', {}), dict):
    err('metadata must be a map of strings')
lines = body.count('\n')
if lines >= 500:
    err(f'SKILL.md body has {lines} lines: keep it under 500')

# references: named in SKILL.md, existing, with a table of contents when long
refs = set(re.findall(r'references/[\w.-]+\.md', body))
for r in sorted(refs):
    p = os.path.join(SKILL, r)
    if not os.path.isfile(p):
        err(f'SKILL.md names {r}, which does not exist')
        continue
    t = open(p, encoding='utf-8').read()
    if t.count('\n') > 100 and '## Contents' not in t:
        err(f'{r} is over 100 lines: open it with a "## Contents" list')
for f in os.listdir(os.path.join(SKILL, 'references')):
    if f'references/{f}' not in refs:
        err(f'references/{f} is not named in SKILL.md: link every reference from SKILL.md (one level deep)')
for f in re.findall(r'scripts/[\w.-]+\.py', body):
    if not os.path.isfile(os.path.join(SKILL, f)):
        err(f'SKILL.md names {f}, which does not exist')
for p in [os.path.join(SKILL, 'SKILL.md')] + [os.path.join(SKILL, 'references', f) for f in os.listdir(os.path.join(SKILL, 'references'))]:
    for n, line in enumerate(open(p, encoding='utf-8'), 1):
        if re.search(r'(scripts|references|assets)\\', line):
            err(f'{os.path.relpath(p, ROOT)}:{n}: a Windows-style path; use forward slashes')

# one version everywhere
plugin = json.load(open(os.path.join(ROOT, '.claude-plugin', 'plugin.json'), encoding='utf-8'))
version = plugin.get('version')
if (fm.get('metadata') or {}).get('version') != version:
    err(f'SKILL.md metadata version {(fm.get("metadata") or {}).get("version")} differs from plugin.json {version}')
ch = open(os.path.join(ROOT, 'CHANGELOG.md'), encoding='utf-8').read() if os.path.isfile(os.path.join(ROOT, 'CHANGELOG.md')) else ''
top = re.search(r'^## \[?(\d+\.\d+\.\d+)', ch, re.M)
if not top or top.group(1) != version:
    err(f'CHANGELOG.md must open with the version in plugin.json ({version})')

# the styles' fonts, palettes and illustrations exist
A = os.path.join(SKILL, 'assets')
pals = json.load(open(os.path.join(A, 'palettes.json'), encoding='utf-8'))
ills = json.load(open(os.path.join(A, 'illustrations.json'), encoding='utf-8'))
for f in sorted(os.listdir(os.path.join(A, 'styles'))):
    s = json.load(open(os.path.join(A, 'styles', f), encoding='utf-8'))
    for role in (s.get('fonts') or {}).values():
        if role and not os.path.isfile(os.path.join(A, 'fonts', role['file'])):
            err(f'styles/{f}: font {role["file"]} is missing')
    for p in [s['palette'], s.get('base_palette')] + s.get('palettes', []):
        if p and p not in pals:
            err(f'styles/{f}: palette {p} is not in palettes.json')
    for k in ('cover_ill', 'default_ill'):
        if s.get(k) and s[k] not in ills:
            err(f'styles/{f}: illustration {s[k]} is missing')

# every script compiles (with the Python running this check; CI runs it on 3.9 too)
for f in sorted(os.listdir(os.path.join(SKILL, 'scripts'))):
    if f.endswith('.py'):
        try:
            py_compile.compile(os.path.join(SKILL, 'scripts', f), doraise=True)
        except py_compile.PyCompileError as e:
            err(f'scripts/{f} does not compile: {e.msg}')

if errors:
    print('FAILED')
    for e in errors:
        print('  - ' + e)
    sys.exit(1)
print(f'OK: {name} {version}; description {len(desc)} chars; SKILL.md body {lines} lines; {len(refs)} references; '
      f'{len(os.listdir(os.path.join(A, "styles")))} styles checked')
