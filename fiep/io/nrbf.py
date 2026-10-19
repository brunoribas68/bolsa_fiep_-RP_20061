"""Leitor mínimo de MS-NRBF (.NET BinaryFormatter), suficiente para os arquivos .nox do NOVA 2.x.

O .nox é o procedimento do NOVA serializado com o BinaryFormatter do .NET. Este módulo
reconstrói o grafo de objetos (classes, campos, arrays) sem depender do NOVA nem do .NET.
Especificação do formato: [MS-NRBF], Microsoft Open Specifications.
"""
from __future__ import annotations

import struct

PRIM = {1: '?', 2: 'B', 6: 'd', 7: 'h', 8: 'i', 9: 'q', 10: 'b', 11: 'f',
        12: 'q', 13: 'Q', 14: 'H', 15: 'I', 16: 'Q'}


class Ref:
    __slots__ = ('id',)
    def __init__(self, i): self.id = i
    def __repr__(self): return f'Ref({self.id})'


class Obj:
    def __init__(self, oid, cls, fields):
        self.id, self.cls, self.fields = oid, cls, fields
    def __repr__(self): return f'Obj({self.cls})'


class Arr:
    def __init__(self, oid, items):
        self.id, self.items = oid, items


class NullN:
    def __init__(self, n): self.n = n


class Reader:
    def __init__(self, data, pos=0):
        self.d, self.p = data, pos
        self.objects = {}
        self.classes = {}  # metadata id -> (name, members, types, addinfo)

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v

    def string(self):
        n, shift = 0, 0
        while True:
            b = self.u8(); n |= (b & 0x7f) << shift; shift += 7
            if not b & 0x80: break
        s = self.d[self.p:self.p + n].decode('utf-8', 'replace'); self.p += n
        return s

    def prim(self, t):
        if t == 18: return self.string()
        if t == 5: return self.string()
        if t == 17: return None
        if t == 3:
            b = self.d[self.p]
            ln = 1 if b < 0x80 else 2 if b < 0xe0 else 3 if b < 0xf0 else 4
            s = self.d[self.p:self.p + ln].decode('utf-8', 'replace'); self.p += ln
            return s
        f = PRIM[t]; v = struct.unpack_from('<' + f, self.d, self.p)[0]
        self.p += struct.calcsize(f); return v

    def classinfo(self):
        oid = self.i32(); name = self.string(); n = self.i32()
        return oid, name, [self.string() for _ in range(n)]

    def typeinfo(self, n):
        bt = [self.u8() for _ in range(n)]
        add = []
        for b in bt:
            if b in (0, 7): add.append(self.u8())
            elif b == 3: add.append(self.string())
            elif b == 4: add.append((self.string(), self.i32()))
            else: add.append(None)
        return bt, add

    def values(self, oid, meta):
        name, members, bt, add = meta
        vals, i = {}, 0
        pending_null = 0
        for k, m in enumerate(members):
            if pending_null:
                vals[m] = None; pending_null -= 1; continue
            if bt is not None and bt[k] == 0:
                vals[m] = self.prim(add[k])
            else:
                r = self.record()
                if isinstance(r, NullN):
                    vals[m] = None; pending_null = r.n - 1
                else:
                    vals[m] = r
        o = Obj(oid, name, vals)
        self.objects[oid] = o
        return o

    def items(self, n, primtype=None):
        out = []
        while len(out) < n:
            if primtype is not None:
                out.append(self.prim(primtype)); continue
            r = self.record()
            if isinstance(r, NullN): out.extend([None] * r.n)
            else: out.append(r)
        return out

    def record(self):
        t = self.u8()
        if t == 0:
            self.p += 16; return self.record()
        if t == 12:
            self.i32(); self.string(); return self.record()
        if t == 1:
            oid = self.i32(); mid = self.i32()
            return self.values(oid, self.classes[mid])
        if t in (2, 3):
            oid, name, mem = self.classinfo()
            if t == 3: self.i32()
            meta = (name, mem, None, None); self.classes[oid] = meta
            return self.values(oid, meta)
        if t in (4, 5):
            oid, name, mem = self.classinfo()
            bt, add = self.typeinfo(len(mem))
            if t == 5: self.i32()
            meta = (name, mem, bt, add); self.classes[oid] = meta
            return self.values(oid, meta)
        if t == 6:
            oid = self.i32(); s = self.string(); self.objects[oid] = s; return s
        if t == 7:
            oid = self.i32(); at = self.u8(); rank = self.i32()
            lens = [self.i32() for _ in range(rank)]
            if at in (3, 4, 5): [self.i32() for _ in range(rank)]
            bt = self.u8()
            ai = None
            if bt in (0, 7): ai = self.u8()
            elif bt == 3: self.string()
            elif bt == 4: self.string(); self.i32()
            n = 1
            for l in lens: n *= l
            a = Arr(oid, self.items(n, ai if bt == 0 else None))
            self.objects[oid] = a; return a
        if t == 8:
            pt = self.u8(); return self.prim(pt)
        if t == 9:
            return Ref(self.i32())
        if t == 10:
            return None
        if t == 11:
            raise StopIteration
        if t == 13:
            return NullN(self.u8())
        if t == 14:
            return NullN(self.i32())
        if t == 15:
            oid = self.i32(); n = self.i32(); pt = self.u8()
            if pt in PRIM:
                f = PRIM[pt]; sz = struct.calcsize(f)
                a = Arr(oid, list(struct.unpack_from(f'<{n}{f}', self.d, self.p)))
                self.p += n * sz
            else:
                a = Arr(oid, [self.prim(pt) for _ in range(n)])
            self.objects[oid] = a; return a
        if t in (16, 17):
            oid = self.i32(); n = self.i32()
            a = Arr(oid, self.items(n)); self.objects[oid] = a; return a
        raise ValueError(f'unknown record {t} at {self.p - 1}')

    def read_stream(self):
        try:
            while True:
                self.record()
        except StopIteration:
            pass
        return self.objects


HEADER = b'\x00\x01\x00\x00\x00\xff\xff\xff\xff\x01\x00\x00\x00\x00\x00\x00\x00'


def read_all(data):
    """Return list of (offset, objects dict) for every serialized stream in the file."""
    out, start = [], 0
    while True:
        i = data.find(HEADER, start)
        if i < 0: break
        r = Reader(data, i)
        try:
            objs = r.read_stream(); out.append((i, objs, r.p))
            start = r.p
        except Exception as e:      # arquivo parcialmente legível: aproveita o que foi lido
            out.append((i, r.objects if r.objects else e, r.p)); start = i + 1
    return out
