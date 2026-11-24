#!/usr/bin/env python3
"""Verify the exact publication allowlist; optionally stage only verified bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
MANIFEST = 'PUBLICATION_SHA256.json'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', action='store_true')
    args = parser.parse_args()
    files = json.loads((ROOT / MANIFEST).read_text())['files_sha256']
    allowed = set(files) | {MANIFEST}
    for name, expected in files.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise SystemExit('Publication hash mismatch: ' + name)
    print('PUBLICATION_FILE_HASHES=PASS', 'N=', len(files))
    if args.stage:
        prior = set(git('ls-files', '-z').decode().split('\0')) - {''}
        if prior - allowed:
            raise SystemExit('Unexpected tracked files: ' + repr(sorted(prior - allowed)))
        subprocess.run(['git', '-C', str(ROOT), 'add', '--', *sorted(allowed)], check=True)
        staged = set(git('ls-files', '-z').decode().split('\0')) - {''}
        if staged != allowed:
            raise SystemExit('Staged allowlist mismatch')
        for name in sorted(allowed):
            if hashlib.sha256(git('show', ':' + name)).hexdigest() != digest(ROOT / name):
                raise SystemExit('Staged byte mismatch: ' + name)
        print('STAGED_ALLOWLIST=PASS', 'N=', len(staged))
        print('NO_ADDITIONAL_FILES_STAGED=YES')
    print('REMOTE_PUSH_PERFORMED=NO')

if __name__ == '__main__':
    main()
