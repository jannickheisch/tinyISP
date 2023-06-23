#

# tinyssb/util.py
# 2022-04-09 <christian.tschudin@unibas.ch>

import base64
import sys
import os
import select

from contextlib import contextmanager

from typing import IO, Generator, Any

if sys.implementation.name == 'micropython':
    import binascii
    fromhex = binascii.unhexlify
    hex = lambda b: binascii.hexlify(b).decode()
else:
    fromhex = lambda h: bytes.fromhex(h)
    hex = lambda b: b.hex()

b64 = lambda b: base64.b64encode(b).decode()

DATA_FOLDER = './data/'
FID_LEN = 32
HASH_LEN = 20
TINYSSB_PKT_LEN = 120
DMX_LEN = 7
DMX_PFX = "tinyssb-v0".encode('utf-8')

PKTTYPE_plain48 = 0
PKTTYPE_chain20 = 1

def byteArrayCmp(a: bytes, b: bytes) -> int:
    for i in range(len(a)):
        d = (a[i] & 0xFF) - (b[i] & 0xFF)
        if d != 0:
            return d
    return 0

@contextmanager
def atomic_write(path, binary = False) -> Generator[IO[Any], None, None]:

    tmp = f'{path}.tmp'
    while os.path.exists(tmp):
        tmp += '.tmp'

    try:
        with open(tmp, 'w+b' if binary else 'w+') as file:
            yield file
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except:
            pass

# wrote our own json.dumps ..
# because micropython's json.dumps() does not know how to pretty print
def json_pp(d, indent=''):
    # extended JSON (prints byte arrays as 0xHEXSEQUENCE)
    def stringify(v):
        if type(v) == bytes:
            return "0x" + v.hex()
        elif type(v) == str:
            return '"' + v + '"'
        return str(v)
    indent += '  '
    if d == None:      return "null"
    # if type(d) == int: return str(d)
    # if type(d) == str: return '"' + d + '"'
    if type(d) == list:
        jsonstr = '[\n'
        cnt = 1
        for i in d:
            jsonstr += indent + json_pp(i, indent)
            jsonstr += ',\n' if cnt < len(d) else  '\n'
            cnt += 1
        jsonstr += indent[:-2] + ']'
        return jsonstr
    if type(d).__name__ in ['dict', 'OrderedDict']:
        jsonstr = '{\n'
        cnt = 1
        for k,v in d.items():
            jsonstr += indent + stringify(k) + ': ' + json_pp(v, indent)
            jsonstr += ',\n' if cnt < len(d) else '\n'
            cnt += 1
        jsonstr += indent[:-2] + '}'
        return jsonstr
    return stringify(d)

def int_to_bytes(val: int) -> bytes:
    return val.to_bytes((val.bit_length() + 7) // 8, "big")

# select.poll() implementation compatible with Windows
# This implementation is limited to select.POLLIN and select.POLLOUT and works only for sockets not file descriptors.
class Poll:

    POLLIN = 1
    POLLOUT = 4

    def __init__(self) -> None:
        self.sockets = {}

    def register(self, socket, eventmask) -> None:
        self.sockets[socket] = eventmask

    def unregister(self, socket) -> None:
        del self.sockets[socket]

    def modify(self, socket, eventmask) -> None:
        self.sockets[socket] = eventmask

    def poll(self, timeout=None) -> list:
        readlist = [socket for socket, eventmask in self.sockets.items() if eventmask & self.POLLIN]
        writelist = [socket for socket, eventmask in self.sockets.items() if eventmask & self.POLLOUT]

        if timeout is not None:
            timeout /= 1000

        rlist, wlist, _ = select.select(readlist, writelist, [], timeout)

        events = []

        for socket in rlist:
            events.append((socket, self.POLLIN))
        for fd in wlist:
            events.append((fd, self.POLLOUT))

        return events
    
   


# eof
