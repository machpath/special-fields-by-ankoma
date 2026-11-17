"""Run on a COPY of a collection (or of an exported .apkg's collection):
lists note types that share field config ids or template ids with another
note type (e.g. made with Manage Note Types > Add > Clone). A note moved
between two such types triggers finding C1 (silent scrambling of the user's
own notes).

Usage: python check_shared_ids.py /path/to/COPY/collection.anki2
"""
import sys
from collections import defaultdict
from anki.collection import Collection

col = Collection(sys.argv[1])
try:
    fid = defaultdict(list)
    tid = defaultdict(list)
    for nt in col.models.all():
        for f in nt["flds"]:
            if f.get("id"):
                fid[f["id"]].append((nt["name"], f["name"]))
        for t in nt["tmpls"]:
            if t.get("id"):
                tid[t["id"]].append((nt["name"], t["name"]))
    shared = defaultdict(set)
    for owners in list(fid.values()) + list(tid.values()):
        names = sorted({o[0] for o in owners})
        if len(names) > 1:
            shared[tuple(names)].add(tuple(owners))
    if not shared:
        print("no note types share field or template ids")
    for names, items in sorted(shared.items()):
        print("SHARED IDS between", names, ":", len(items), "fields/templates")
finally:
    col.close(downgrade=False)
