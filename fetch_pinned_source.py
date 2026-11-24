#!/usr/bin/env python3
"""Opt-in network retrieval of the published source. Does not grant redistribution rights."""
import argparse, hashlib, json, tempfile, urllib.request
from pathlib import Path
from turn_intake_pinned import DATASET,FILE,REVISION,SHA256

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',type=Path,required=True);p.add_argument('--confirm-local-use',action='store_true');a=p.parse_args()
    if not a.confirm_local_use:p.error('Check source terms first, then pass --confirm-local-use; never redistribute source or verbatim labels by default')
    root=a.destination.expanduser().resolve();repo=Path(__file__).resolve().parent
    if root==repo or repo in root.parents:p.error('Destination must be outside repository')
    root.mkdir(parents=True,exist_ok=True);dest=root/FILE;manifest=root/'source_manifest.json'
    url=f'https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{FILE}'
    def digest(path):
        with path.open('rb') as f:
            h=hashlib.sha256()
            for b in iter(lambda:f.read(1048576),b''):h.update(b)
            return h.hexdigest()
    if not dest.exists():
        with tempfile.TemporaryDirectory(dir=root) as td:
            temp=Path(td)/FILE
            with urllib.request.urlopen(url,timeout=120) as r,temp.open('wb') as f:
                for b in iter(lambda:r.read(1048576),b''):f.write(b)
            if digest(temp)!=SHA256:raise RuntimeError('Downloaded bytes do not match the pinned SHA-256')
            if dest.exists():raise RuntimeError('Destination appeared during download; refusing overwrite')
            temp.rename(dest)
    if digest(dest)!=SHA256:raise RuntimeError('Existing file differs from pinned source; refusing overwrite')
    info={'dataset':DATASET,'file':FILE,'commit':REVISION,'sha256':SHA256,'url':url}
    if manifest.exists():
        old=json.loads(manifest.read_text())
        if any(old.get(k)!=info[k] for k in ('dataset','file','commit','sha256')):raise RuntimeError('Existing manifest mismatch')
    else:manifest.write_text(json.dumps(info,indent=2)+'\n')
    print('SOURCE_SHA256=PASS');print('LOCAL_SOURCE='+str(dest));print('LOCAL_MANIFEST='+str(manifest))
if __name__=='__main__':main()
