#

# tinyssb/node.py   -- node (peering and replication) behavior
# 2022-04-09 <christian.tschudin@unibas.ch>


import hashlib
import _thread
from typing import Callable, Optional, Type
import bipf
import os

from .keystore import Keystore
from . import io, util, repo


LOGTYPE_private = 0x00  # private fid (not to be shared)
LOGTYPE_public  = 0x01  # public fid to synchronise with peers
LOGTYPE_remote  = 0x02  # public fid from a remote peer

NOVELTY_LEN = 33
FID_LEN = 32
novelty_credit = 1
DMX_PFX = "tinyssb-v0".encode('utf-8')
DMX_LEN = 7
TINYSSB_PKT_LEN = 120
HASH_LEN = 20

class Novelty:
    type = 'n'
    key = bytearray(FID_LEN)
    wire = bytearray(0)

class Dmx:
    
    def __init__(self, dmx: bytes, fct: Callable[[bytes, Optional[bytes]], None], aux: Optional[bytes] = None) -> None:
        self.dmx = dmx
        self.fct = fct
        self.aux = aux

class Chunk:

    def __init__(self, h: bytes, fct: Callable[[bytes, int], None], fid: bytes, seq: int, bnr: int) -> None:
        self.h = h
        self.fct = fct
        self.fid = fid
        self.seq = seq
        self.bnr = bnr



class NODE:  # a node in the tinySSB forwarding fabric

    def __init__(self, faces: list[Type[io.FACE]], keystore: Keystore, me: bytes, callback: Optional[Callable[[repo.LogTinyEntry], None]] = None):
        from . import goset
        self.faces = faces
        self.ks = keystore
        _, name = self.ks.kv[me]
        self.dmxt: list[Dmx] = []  # DMX  ~ dmx_tuple  DMX filter bank
        self.blbt: list[Chunk]  = []    # hptr ~ blob_obj  blob filter bank
        self.timers = []
        self.comm = {}
        self.me = me
        self.next_timeout = [0]
        self.ndlock = _thread.allocate_lock()

        self.goset_manager = goset.GOsetManager(self)
        self.goset = self.goset_manager.add_goset("tinySSB-0.1 GOset 1", 0)
        
        self.repo = repo.Repo(self, os.path.join(util.DATA_FOLDER, name), self.goset)
        
        self.log_offs = 0
        self.callback= callback
        
    def on_tiny_event(self, tiny_event: repo.LogTinyEntry) -> None:
        print("received:", tiny_event)
        if self.callback is not None:
            self.callback(tiny_event)

    def start(self) -> None:
        self.ioloop = io.IOLOOP(self.faces, self.on_rx)

        if self.me.hex() not in os.listdir(self.repo.FEED_DIR):
            self.repo.new_feed(self.me, repo.FEED_TYPE_ROOT)
        #fdir = File(context.getDir(Constants.TINYSSB_DIR, Context.MODE_PRIVATE), context.tinyRepo.FEED_DIR)
        # dbg(TERM_NORM, '  starting thread with IO loop')
        self.repo.repo_load()
        print(self.me.hex())

        #self.arm_dmx(self.goset.goset_dmx,  lambda buf, aux: self.goset.rx(buf, aux))

        _thread.start_new_thread(self.ioloop.run, tuple())
        # dbg(TERM_NORM, "  starting thread with arq loop")
        _thread.start_new_thread(self.goset_manager.loop, tuple())
        #_thread.start_new_thread(self.arq_loop, tuple())

    def dmxt_find(self, dmx: bytes) -> Optional[Dmx]:
        for d in self.dmxt:
            if dmx == d.dmx:
                return d

        return None

    def arm_dmx(self, dmx: bytes, fct: Optional[Callable] = None, aux: Optional[bytes] = None) -> None:
        d = self.dmxt_find(dmx)
        if fct is None and d is not None:
            self.dmxt.remove(d)
            return
        if d is None and fct is not None:
            d = Dmx(dmx, fct, aux)
            self.dmxt.append(d)


    def blbt_find(self, h: bytes) -> Optional[Chunk]:
        for b in self.blbt:
            if h == b.h:
                return b

        return None


    def arm_blob(self, h: bytes, fct: Optional[Callable[[bytes, int], None]] = None,
                  fid: Optional[bytes] = None, seq = -1, bnr = -1) -> None:
        b = self.blbt_find(h)
        if fct is None and b is not None:
            self.blbt.remove(b)
        if b is None and fct is not None and fid is not None:
            b = Chunk(h, fct, fid, seq, bnr)
            self.blbt.append(b)


    def on_rx(self, buf: bytes, neigh) -> bool:
        """
        Manages the reception from all interfaces
        :param buf: the message
        :param neigh: Interfaces available (added in IOLOOP.run)
        :return: nothing
        """
        # all tSSB packet reception logic goes here!
        # dbg(GRE, "<< buf", len(buf), util.hex(buf[:20]), "...")
        # if len(buf) == 120:
            # try: dbg(RED, "<< is", bipf.loads(buf[8:56]))#, "...", buf[:7] in self.dmxt)
            # except: pass
        h = hashlib.sha256(buf).digest()[:HASH_LEN]
        rc = False
        d = self.dmxt_find(buf[:DMX_LEN])
        if d is not None:
            print(d.fct)
            d.fct(buf, d.aux)
        if len(buf) == TINYSSB_PKT_LEN:
            b = self.blbt_find(h)
            if b is not None:
                b.fct(buf, self.blbt.index(b))
                rc = True
        print("could not find dmx")
        return rc


    def publish_public_content(self, content: bytes, pk: Optional[bytes] = None) -> bool:
        if pk is None:
            pk = self.me
        pkt = self.repo.mk_content_log_entry(pk, content)
        print("pub:",len(content))
        if pkt is None:
            return False
        return self.repo.feed_append(pk, pkt)

    # ----------------------------------------------------------------------

    # def incoming_want_request(self, buf: bytes, aux:Optional[bytes] = None, neigh: Optional[io.FACE] = None) -> None:
    #     """
    #     Handle want request.
        
    #     """
    #     print("incoming want")

    #     lst = bipf.loads(buf[DMX_LEN:])
    #     if not lst or type(lst) is not list:
    #         print("error decoding want request")
    #         return
    #     if len(lst) < 1 or type(lst[0]) is not int:
    #         print("error decoding want request with offset")
    #         return
    #     offs = lst[0]
    #     v = "WANT vector=["
    #     credit = 3
    #     for i in range(1, len(lst)):
    #         try:
    #             ndx = (offs + i - 1) % len(self.goset.keys)
    #             fid = self.goset.keys[ndx]
    #             seq = lst[i]
    #             v += f' {ndx}.{seq}'
    #         except:
    #             print("error incoming Want error")
    #             continue
    #     while credit > 0:
    #         log = self.repo.get_log(fid)
    #         if len(log) < seq:
    #             break
    #         pkt = log[seq]
    #         print("NODE have entry", fid.hex(),".",seq)
    #         print("entry:",pkt.dmx.hex())
    #         for f in self.faces:
    #             f.enqueue(pkt.wire)
    #         seq += 1
    #         credit -= 1

    #     v += " ]"
    #     print("Node", v)
    #     if credit == 3:
    #         print("Node no entry found to serve")

    # def incoming_chunk_request(self, demx, buf, neigh):
    #     print("Node incoming CHNK request")
    #     vect = bipf.loads(buf[DMX_LEN:])
    #     if vect == None or type(vect) != list:
    #         print("Node error decoding CHNK request")
    #         return
    #     print(vect)
    #     v = "CHNK vector=["
    #     credit = 3
    #     for e in vect:
    #         try:
    #             fNDX = e[0]
    #             fid = self.goset.keys[fNDX]
    #             seq = e[1]
    #             cnr = e[2]
    #             v += f" {fid.hex()}.{seq}.{cnr}"
    #         except Exception as e:
                
    #             print("Node incoming CHNK error")
    #             print(e)
    #             continue
    #         try:
    #             pkt = self.repo.get_log(fid)[seq]
    #         except:
    #             pkt = None
            
    #         if pkt is None or int.from_bytes(pkt.typ) != util.PKTTYPE_chain20:
    #             continue
    #         (sz, szlen) = bipf.varint_decode_max(pkt.wire, DMX_LEN + 1, DMX_LEN + 4)
    #         if(sz <= 28 - szlen):
    #             continue
    #         maxChunks = (sz - (28 - szlen) + 99) / 100
    #         if cnr > maxChunks:
    #             continue
    #         while(cnr <= maxChunks and credit > 0):
    #             credit -= 1
    #             chunk = self.repo.get_blob(fid, seq, cnr)
    #             print("CHUNK:", chunk)
    #             if chunk is None:
    #                 print("could not find chunk")
    #                 break
    #             for f in self.faces:
    #                 f.enqueue(chunk)
    #             cnr += 1
    #     v += " ]"
    #     print("Node", v)


    def incoming_pkt(self, buf: bytes, fid: bytes) -> None:
        print("imncoming pkt", fid.hex())
        if len(buf) != TINYSSB_PKT_LEN:
            return
        self.repo.feed_append(fid, buf)

    def incoming_chainedblob(self, buf: bytes, blbt_ndx: int) -> None:
        print("incoming chunk")
        if len(buf) != TINYSSB_PKT_LEN:
            return
        self.repo.sidechain_append(buf, blbt_ndx)

    # def arq_loop(self):  # Automatic Repeat reQuest
    #     while True:
    #         v = ""
    #         vect = []
    #         encoding_len = 0
    #         self.log_offs = (self.log_offs + 1) % len(self.goset.keys)
    #         vect.append(self.log_offs)
    #         i = 0
    #         while i < len(self.goset.keys):
    #             ndx = (self.log_offs + i) % len(self.goset.keys)
    #             key = self.goset.keys[ndx]
    #             feed = self.repo.get_log(key)
    #             bptr = feed.frontS + 1
    #             vect.append(bptr)

    #             dmx = packet._dmx(key + bptr.to_bytes(4, 'big') + feed.frontM)
    #             print("arm", dmx.hex(), f"for {key.hex()}.{bptr}")
    #             self.arm_dmx(dmx, lambda buf, n: self.incoming_logentry(dmx,
    #                                                         feed, buf, n))
    #             v += ("[ " if len(v) == 0 else ", ") + f'{ndx}.{bptr}'
    #             i += 1
    #             encoding_len += len(bipf.dumps(bptr))
    #             if encoding_len > 100:
    #                 break

    #         self.log_offs = (self.log_offs + i) % len(self.goset.keys)
    #         if len(vect) > 1:
    #             wire = self.want_dmx + bipf.dumps(vect)
    #             for f in self.faces:
    #                 f.enqueue(wire)
    #         print(">> sent WANT request", v, "]")

    #         chunk_req_list = []
    #         for c in self.pending_chains:
    #             fid, seq, blbt_ndx = self.pending_chains[c]
    #             fid_nr = next(i for i, x in enumerate(self.goset.keys) if util.byteArrayCmp(x, fid) == 0)
    #             chunk_req_list.append([fid_nr, seq, blbt_ndx])

    #         if chunk_req_list:
    #             wire = self.chnk_dmx + bipf.dumps(chunk_req_list)
    #             for f in self.faces:
    #                 f.enqueue(wire)
    #                 print(">> sent CHK request:", chunk_req_list)
    #         time.sleep(5)

# eof
