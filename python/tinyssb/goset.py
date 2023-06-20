import hashlib
from collections import deque
from . import node, io, repo, util #NODE, LOGTYPE_remote

import time

import functools
import os

from typing import Any, Callable, Optional
import bipf


GOSET_DMX_STR = "tinySSB-0.1 GOset 1"
DMX_PFX = b"tinyssb-v0"


class Claim:
    typ = b'c'
    lo = bytes(0)  # util.FID_LEN
    hi = bytes(0)  # util.FID_LEN
    xo = bytes(0)  # util.FID_LEN
    sz = 0
    wire = bytes(0)


class Novelty:
    typ = b'n'
    key = bytes(util.FID_LEN)
    wire = bytes(0)


NOVELTY_LEN = 33 # sizeof(struct novelty_s)
CLAIM_LEN = 98 # sizeof(struct claim_s)
ZAP_LEN = 33 # sizeof(struct zap_s)

GOSET_KEY_LEN   = util.FID_LEN
GOSET_MAX_KEYS  =    100
GOSET_ROUND_LEN = 10
MAX_PENDING     =     20
NOVELTY_PER_ROUND =    1
ASK_PER_ROUND   =      1
HELP_PER_ROUND  =      2
ZAP_ROUND_LEN   =   4500






class GOset():

    def __init__(self, node: node.NODE, dmx_str: str =GOSET_DMX_STR, epoch: int = 0,
                 add_key_callback: Optional[Callable[[bytes], None]] = None) -> None:
        self.node = node
        self.dmx_str = dmx_str # for isp: dmx_str = GOSET_DMX_STR + contractID
        self.epoch = epoch
        self.is_root_goset = dmx_str == GOSET_DMX_STR
        self.goset_dmx = hashlib.sha256(self.dmx_str.encode() + (epoch.to_bytes() if not self.is_root_goset else b"") ).digest()[:util.DMX_LEN]
        self.want_dmx = self.compute_dmx('want'.encode('utf-8') + self.state)
        self.chunk_dmx = self.compute_dmx('blob'.encode('utf-8') + self.state)
        # self.novelt_and_claim_dmx = hashlib.sha256(self.dmx_str.encode()).digest()[:util.DMX_LEN]
        self.node.arm_dmx(self.goset_dmx, lambda pkt, aux: self.rx(pkt))
        self.add_key_callback = add_key_callback

    state = bytearray(util.FID_LEN)
    keys = []
    pending_claims = []
    pending_novelty = deque()
    largest_claim_span = 0
    novelty_credit = 1

    def loop(self) -> None:
        while True:
            self.beacon()
            time.sleep(GOSET_ROUND_LEN)


    def rx(self, pkt: bytes, aux: Optional[bytes] = None) -> None:
        
        if len(pkt) <= util.DMX_LEN:
            return
        
        dmx = pkt[:util.DMX_LEN]

        print("received len:", len(pkt))
        print("dmx:", dmx.hex(), "but expected:", self.goset_dmx.hex())

        # sanity check, GosetHandler should ensure this
        if dmx != self.goset_dmx: 
            print("Unknown novelty / claim dmx")
            return
        
        pkt = pkt[util.DMX_LEN:] # remove dmx

        if len(pkt) == NOVELTY_LEN and pkt[0] == ord('n'):

            print("received Novelty")
            self._add_key(pkt[1:NOVELTY_LEN])
            return
        
        if len(pkt) != CLAIM_LEN or pkt[0] != ord('c'):
            print("not claim")
            return
        
        cl = self._mk_claim_from_bytes(pkt)

        if cl.sz > self.largest_claim_span:
            self.largest_claim_span = cl.sz
        if cl.sz == len(self.keys) and util.byteArrayCmp(self.state, cl.xo) == 0:
            print("GOset rx(): seems we are synced (with at least someone), |GOset|=",
                   len(self.keys))
        else:
            self._add_key(cl.lo)
            self._add_key(cl.hi)
            self._add_pending_claim(cl)
            print("add pending claim")


    def beacon(self) -> None:
        if len(self.keys) == 0:
            return
        while(self.novelty_credit > 0 and len(self.pending_novelty) > 0):
            self.novelty_credit -= 1
            self._enqueue(self.pending_novelty.popleft().wire, self.goset_dmx, None)
        self.novelty_credit = NOVELTY_PER_ROUND
        cl = self._mk_claim(0, len(self.keys) - 1)
        if util.byteArrayCmp(cl.xo, self.state) != 0:
            print("GOset state change to", cl.xo.hex(), "|keys|=", len(self.keys))
            self.state = cl.xo
            self.update_want_dmx()
        self._enqueue(cl.wire, self.goset_dmx, None)

        self.pending_claims.sort(key=lambda x: x.sz)
        max_ask = ASK_PER_ROUND
        max_help = HELP_PER_ROUND

        retain: list[Claim] = []
        for c in self.pending_claims:
            if c.sz == 0:
                return
            lo = next(i for i, x in enumerate(self.keys) if util.byteArrayCmp(x, c.lo) == 0)
            hi = next(i for i, x in enumerate(self.keys) if util.byteArrayCmp(x, c.hi) == 0)
            if lo == -1 or hi == -1 or lo > hi:
                continue
            partial = self._mk_claim(lo,hi)
            if util.byteArrayCmp(partial.xo, c.xo) == 0:
                continue
            if partial.sz <= c.sz:
                if max_ask > 0:
                    self._enqueue(partial.wire, self.goset_dmx, None)
                    max_ask -= 1
                if partial.sz < c.sz:
                    retain.append(c)
                    continue

            if max_help > 0:
                max_help -= 1
                hi -= 1
                lo += 1
                if hi <= lo:
                    self._enqueue(self._mk_novelty_from_key(self.keys[lo]).wire, 
                                  self.goset_dmx, None)
                elif hi - lo <= 2:
                    self._enqueue(self._mk_claim(lo,hi).wire, self.goset_dmx, None)
                else:
                    sz = (hi + 1 -lo) // 2
                    self._enqueue(self._mk_claim(lo,lo+sz-1).wire, self.goset_dmx, None)
                    self._enqueue(self._mk_claim(lo+sz, hi).wire, self.goset_dmx, None)
                continue
            retain.append(c)

        while len(retain) >= MAX_PENDING - 5:
            retain.pop()
        self.pending_claims = retain


    def _include_key(self, key: bytes) -> bool:
        zero = bytes(GOSET_KEY_LEN)
        if key == zero:
            return False
        if key in self.keys:
            print("GOset _include_key(): key already exists")
            return False
        if len(self.keys) >= GOSET_MAX_KEYS:
            print("GOset _include_key(): too many keys")
            return False
        print("GOset _include_key", key)
        self.keys.append(key)
        return True


    def _add_key(self, key: bytes) -> None:
        if not self._include_key(key):
            return
        typ = repo.FEED_TYPE_ROOT if self.is_root_goset else repo.FEED_TYPE_ISP_VIRTUAL
        self.node.repo.new_feed(key, typ)

        self.keys = sorted(self.keys, key=functools.cmp_to_key(util.byteArrayCmp))
        print("ADDKEY: ", self.keys)
        if len(self.keys) >= self.largest_claim_span:
            n = self._mk_novelty_from_key(key)
            if self.novelty_credit > 0:
                self._enqueue(n.wire, self.goset_dmx)
                self.novelty_credit -= 1
            elif len(self.pending_novelty) < MAX_PENDING:
                self.pending_novelty.append(n)
        print("GOSET _add_key(): added key", key)

        if self.add_key_callback is not None:
            self.add_key_callback(key)


    def _add_pending_claim(self, cl: Claim) -> None:
        for c in self.pending_claims:
            if c.sz == cl.sz and c.xo == cl.xo:
                return
        self.pending_claims.append(cl)


    def _mk_novelty_from_key(self, key: bytes) -> Novelty:
        n = Novelty()
        n.wire = bytes(b'n') + key
        n.key = key
        return n


    def _mk_claim_from_bytes(self, pkt: bytes) -> Claim:
        cl = Claim()
        cl.lo = pkt[1:33]
        cl.hi = pkt[33:65]
        cl.xo = pkt[65:97]
        cl.sz = pkt[97]
        cl.wire = pkt
        return cl


    def _mk_claim(self, lo: int, hi: int) -> Claim:
        cl = Claim()
        cl.lo = self.keys[lo]
        cl.hi = self.keys[hi]
        cl.xo = self._xor(lo, hi)
        cl.sz = hi - lo + 1
        b = cl.sz.to_bytes()
        cl.wire = cl.typ + cl.lo + cl.hi + cl.xo + b
        return cl


    def _xor(self, lo: int, hi: int) -> bytearray:
        xor = bytearray(self.keys[lo])
        for k in self.keys[lo+1 : hi+1]:
            for i in range(len(xor)):
                xor[i] ^= k[i]
        return xor


    def _enqueue(self, buf: bytes, dmx: Optional[bytes] = None,
                  aux: Optional[bytes] = None) -> None:
        pkt = buf if dmx is None else dmx + buf
        for f in self.node.faces:
            f.enqueue(pkt)


    def adjust_state(self) -> None:
        self.keys = sorted(self.keys, key=functools.cmp_to_key(util.byteArrayCmp))
        if len(self.keys) > 0:
            cl = self._mk_claim(0, len(self.keys)-1)
            self.state = cl.xo
        else:
            self.state = bytes(util.FID_LEN)
        print("GOset adjust_state() for", len(self.keys), "resulted in", self.state.hex())
        self.update_want_dmx()

    @staticmethod
    def compute_dmx(buf: bytes) -> bytes:
        return hashlib.sha256(DMX_PFX + buf).digest()[:util.DMX_LEN]
    
    def set_add_key_callback(self, callback: Callable[[bytes], None]) -> None:
        self.add_key_callback = callback


    def update_want_dmx(self) -> None:
        print("update want")
        self.node.arm_dmx(self.want_dmx, None, None)
        self.node.arm_dmx(self.chunk_dmx, None, None)

        self.want_dmx = self.compute_dmx('want'.encode('utf-8') + self.state)
        self.chunk_dmx = self.compute_dmx('blob'.encode('utf-8') + self.state)

        print("set want to:", self.want_dmx.hex())

        self.node.arm_dmx(self.want_dmx,
                          lambda buf, aux: self.incoming_want_request(buf, None, None))
        self.node.arm_dmx(self.chunk_dmx,
                          lambda buf, aux: self.incoming_chunk_request(buf, None, None))
        
    def incoming_want_request(self, buf: bytes, aux:Optional[bytes] = None, neigh: Optional[io.FACE] = None) -> None:
        """
        Handle want request.
        
        """
        print("incoming want")

        lst = bipf.loads(buf[util.DMX_LEN:])
        if not lst or type(lst) is not list:
            print("error decoding want request")
            return
        if len(lst) < 1 or type(lst[0]) is not int:
            print("error decoding want request with offset")
            return
        offs = lst[0]
        v = "WANT vector=["
        credit = 3
        for i in range(1, len(lst)):
            try:
                ndx = (offs + i - 1) % len(self.keys)
                fid = self.keys[ndx]
                seq = lst[i]
                v += f' {ndx}.{seq}'
            except:
                print("error incoming Want error")
                continue
            while credit > 0:
                pkt = self.node.repo.feed_read_pkt(fid, seq)
                if pkt is None:
                    break
                print("NODE have entry", fid.hex(),".",seq)
                for f in self.node.faces:
                    f.enqueue(pkt)
                seq += 1
                credit -= 1

        v += " ]"
        print("Node", v)
        if credit == 3:
            print("Node no entry found to serve")

    def incoming_chunk_request(self, buf: bytes, aux: Optional[bytes], neigh: Optional[io.FACE]) -> None:
        print("Node incoming CHNK request")
        vect = bipf.loads(buf[util.DMX_LEN:])
        if vect == None or type(vect) != list:
            print("Node error decoding CHNK request")
            return
        print(vect)
        v = "CHNK vector=["
        credit = 3
        for e in vect:
            try:
                fNDX = e[0]
                fid = self.keys[fNDX]
                seq = e[1]
                cnr = e[2]
                v += f" {fid.hex()}.{seq}.{cnr}"
            except Exception as e:
                print("Node incoming CHNK error")
                print(e)
                continue
            
            pkt = self.node.repo.feed_read_pkt(fid, seq)
            if pkt is None or pkt[util.DMX_LEN] != util.PKTTYPE_chain20:
                continue
            (sz, szlen) = bipf.varint_decode_max(pkt, util.DMX_LEN + 1, util.DMX_LEN + 4)
            if(sz <= 28 - szlen):
                continue
            maxChunks = (sz - (28 - szlen) + 99) // 100
            if cnr > maxChunks:
                continue
            while(cnr <= maxChunks and credit > 0):
                credit -= 1
                chunk = self.node.repo.feed_read_chunk(fid, seq, cnr)
                print("CHUNK:", chunk)
                if chunk is None:
                    print("could not find chunk")
                    break
                for f in self.node.faces:
                    f.enqueue(chunk)
                cnr += 1
        v += " ]"
        print("Node", v)


class GOsetManager():
    def __init__(self, node: node.NODE) -> None:
        self.sets: set[GOset] = set()
        self.node = node
        self.offs: dict[GOset, int] = {}

    def loop(self) -> None:
        while True:
            self.arq_loop()
            for go in self.sets:
                go.beacon()
            time.sleep(GOSET_ROUND_LEN)

    def add_goset(self, dmx_str: str =GOSET_DMX_STR, epoch: int = 0,
                 add_key_callback: Optional[Callable[[bytes], None]] = None) -> GOset:
        go = GOset(self.node, dmx_str, epoch, add_key_callback)
        self.sets.add(go)
        self.offs[go] = 0

        return go

    def remove_goset(self, goset: GOset) -> bool:
        for go in self.sets:
            if goset == go:
                self.node.arm_dmx(go.goset_dmx) # rmv goset_dmx handler
                self.sets.remove(go)
                del self.offs[go]
                return True
        return False

    def arq_loop(self) -> None:
        for go in self.sets:
            v = ""
            vect = []
            encoding_len = 0
            self.offs[go] = (self.offs[go] + 1) % len(go.keys)
            vect.append(self.offs[go])
            i = 0
            while i < len(go.keys):
                ndx = (self.offs[go] + i) % len(go.keys)
                key = go.keys[ndx]
                feed = self.node.repo.fid2rec(key)
                if feed is None:
                    continue
                bptr = feed.next_seq
                vect.append(bptr)

                dmx = go.compute_dmx(key + bptr.to_bytes(4, 'big') + feed.prev_hash)
                print("arm", dmx.hex(), f"for {key.hex()}.{bptr}")
                self.node.arm_dmx(dmx, lambda buf, fid: self.node.incoming_pkt(buf, fid), key)
                v += ("[ " if len(v) == 0 else ", ") + f'{ndx}.{bptr}'
                i += 1
                encoding_len += len(bipf.dumps(bptr))
                if encoding_len > 100:
                    break

            self.offs[go] = (self.offs[go] + i) % len(go.keys)
            if len(vect) > 1:
                wire = go.want_dmx + bipf.dumps(vect)
                for f in self.node.faces:
                    f.enqueue(wire)
            print(">> sent WANT request", v, "]")
            

            # TODO CHUNK REQUEST

            chunk_req_list = []
            for f in os.listdir(self.node.repo.FEED_DIR):
                if not os.path.isdir(os.path.join(self.node.repo.FEED_DIR, f)) or len(f) != 2* util.FID_LEN:
                    continue
                fid = util.fromhex(f)
                frec = self.node.repo.fid2rec(fid, True)
                if frec is None:
                    continue
                frec.next_seq = self.node.repo.feed_len(fid) + 1
                for fn in os.listdir(os.path.join(self.node.repo.FEED_DIR, f)):
                    path = os.path.join(os.path.join(self.node.repo.FEED_DIR, f), fn)
                    if not fn.startswith("!"):
                        continue
                    seq = int(fn[1:])
                    sz = os.path.getsize(path)
                    h = bytes(util.HASH_LEN)
                    if sz == 0:
                        pkt = self.node.repo.feed_read_pkt(fid, seq)
                        if pkt is not None:
                            h = pkt[util.DMX_LEN + 1 + 28:util.DMX_LEN + 1 + 28 + util.HASH_LEN]
                        else:
                            seq -= 1
                    else:
                        with open(path, "rb") as g:
                            g.seek(-util.HASH_LEN, 2) # seek from end of file
                            if g.read(len(h)) != len(h):
                                seq -= 1
                            else:
                                i = 0
                                while i < util.HASH_LEN:
                                    if h[i] != 0:
                                        break
                                    else:
                                        i += 1
                                if i == util.HASH_LEN:
                                    seq -= 1
                    
                    if seq > 0:
                        next_chunk = sz // util.TINYSSB_PKT_LEN
                        fidNr = go.keys.index(fid)
                        lst = [fidNr, seq, next_chunk]
                        chunk_req_list.append(lst)
                        self.node.arm_blob(h, lambda pkt, x: self.node.incoming_chainedblob(pkt, x), fid, seq, next_chunk)

            if chunk_req_list:
                wire = go.chunk_dmx + bipf.dumps(chunk_req_list)
                for f in self.node.faces:
                    f.enqueue(wire)







