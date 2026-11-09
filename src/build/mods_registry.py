from __future__ import print_function

import glob
import json
import os


def find_repo(start):
    current = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(current, 'src', 'mods')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    fallback = os.path.abspath(os.path.join(os.getcwd(), 'scratch', 'gh_repo'))
    if os.path.isdir(os.path.join(fallback, 'src', 'mods')):
        return fallback
    return None


def expand(value, ver):
    if isinstance(value, str):
        return value.replace('{ver}', ver)
    if isinstance(value, list):
        return [expand(item, ver) for item in value]
    if isinstance(value, dict):
        return dict((key, expand(item, ver)) for key, item in value.items())
    return value


def load_mods(repo):
    mods = []
    for path in sorted(glob.glob(os.path.join(repo, 'src', 'mods', '*', 'mod.json'))):
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        data['_file'] = path
        for field in ('folder', 'id', 'title', 'version', 'files'):
            if field not in data:
                raise ValueError('%s: missing %s' % (path, field))
        mods.append(data)
    mods.sort(key=lambda item: item['folder'])
    folders = set()
    ids = set()
    for mod in mods:
        if mod['folder'] in folders:
            raise ValueError('duplicate folder %s' % mod['folder'])
        if mod['id'] in ids:
            raise ValueError('duplicate id %s' % mod['id'])
        folders.add(mod['folder'])
        ids.add(mod['id'])
    return mods
