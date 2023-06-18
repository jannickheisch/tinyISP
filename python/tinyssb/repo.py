import hashlib
from .node import NODE
from . import util
from .goset import GOset
from .util import PKTTYPE_chain20, PKTTYPE_plain48, DMX_LEN, TINYSSB_PKT_LEN, HASH_LEN, DMX_PFX
import bipf
import shutil

import os
from typing import Optional, Any, IO

FEED_TYPE_ROOT = "root_feed"
FEED_TYPE_ISP_VIRTUAL = "isp_virtual_feed"

class Feed:

    def __init__(self, fid: bytes, typ:str) -> None:
        self.fid = fid
        self.next_seq = 1
        self.prev_hash = fid
        self.type = typ

    def __len__(self) -> int:
        return self.next_seq - 1


class LogTinyEntry:

    def __init__(self, fid: bytes, seq: int, mid: bytes, body: bytes) -> None:
        self.fid = fid
        self.seq = seq
        self.mid = mid # msg hash
        self.body = body # Bipf(APP,XRF,OTHERDATA)

class Repo:

    def __init__(self, node: NODE, path: str, root_go_set: GOset) -> None:
        self.node = node
        self.path = path
        self.root_go_set = root_go_set
        self.FEED_DIR = os.path.join(path, "feeds")
        os.makedirs(self.FEED_DIR, exist_ok=True)
        self.feeds: list[Feed] = []


    def _feed_index(self, fid: bytes) -> int:
        for i, feed in enumerate(self.feeds):
            if feed.fid == fid:
                return i
            
        return -1


    def fid2rec(self, fid: bytes, create_if_needed: bool = False, feed_type: str = FEED_TYPE_ROOT) -> Optional[Feed]:
        feed = next((f for f in self.feeds if f.fid == fid))

        if feed is not None:
            return feed

        if not create_if_needed:
            return None
        
        frec = Feed(fid, feed_type)
        self.feeds.append(frec)
        return frec
    

    def _open_file(self, fid: bytes, mode: str, seq: int = -1, blob_indx: int = -1) -> IO[Any]:
        feed_dir = os.path.join(self.FEED_DIR, fid.hex())
        os.makedirs(feed_dir, exist_ok=True)
        fn = ""
        if blob_indx == -1:
            fn = "mid" if seq >= 0 else "log"
        elif blob_indx > 0:
            fn = "!" + str(seq)
        else:
            fn = "-" + str(seq)
        f = os.path.join(feed_dir, fn)
        if not os.path.exists(f):
            with open(f, "w+"):
                pass
            if fn == "log" :
                with open(os.path.join(feed_dir, "mid"), "w+"):
                    pass

        return open(f, mode=mode)
    
    
    def repo_clean(self, dir: str) -> None:
        shutil.rmtree(dir)
    
    def repo_reset(self) -> None:
        self.repo_clean(self.FEED_DIR)

    def repo_load(self) -> None:
        for f in os.listdir(self.FEED_DIR):
            path = os.path.join(self.FEED_DIR, f)
            if not os.path.isdir(path) or len(f) != 2 * util.FID_LEN:
                continue
            fid = util.fromhex(f)
            ndx = self._feed_index(fid)
            if ndx < 0:
                ndx = len(self.feeds)
                typ = FEED_TYPE_ROOT
                if FEED_TYPE_ISP_VIRTUAL in os.listdir(path):
                    typ = FEED_TYPE_ISP_VIRTUAL
                self.feeds.append(Feed(fid, typ))
            frec = self.feeds[ndx]
            frec.next_seq = self.feed_len(fid) + 1
            m = os.path.join(path, "mid")
            if not os.path.exists(m):
                with open(m, "w+"):
                    pass
            if os.path.getsize(m) >= HASH_LEN:
                with open(m, "rb") as f:
                    f.seek(os.path.getsize(m) - HASH_LEN)
                    frec.prev_hash = f.read()

        for f in self.feeds:
            if f.type == FEED_TYPE_ROOT:
                self.root_go_set._include_key(f.fid)
        self.root_go_set.adjust_state()


    def new_feed(self, fid: bytes, feed_type = FEED_TYPE_ROOT) -> None:
        fdir = os.path.join(self.FEED_DIR, fid.hex())
        try:
            self.repo_clean(fdir)
        except:
            pass
        os.makedirs(fdir, exist_ok=True)
        with open(os.path.join(fdir, feed_type), "w+"):
            pass
        with open(os.path.join(fdir, "log"), "w+"):
            pass
        with open(os.path.join(fdir, "mid"), "w+"):
            pass
        self.feeds.append(Feed(fid, feed_type))

    def feed_read_mid(self, fid: bytes, seq: int) -> Optional[bytes]:
        if seq < 1:
            return None
        fdir = os.path.join(self.FEED_DIR, fid.hex())
        fmid = os.path.join(fdir, "mid")
        with open(fmid, "rb") as f:
            f.seek(HASH_LEN * (seq-1))
            buf = f.read(HASH_LEN)
        return buf if (len(buf) == HASH_LEN) else None

    def feed_read_pkt(self, fid: bytes, seq: int) -> Optional[bytes]:
        if seq < 1:
            return None

        with self._open_file(fid, "rb", -1) as f:
            if os.path.getsize(f.name)/TINYSSB_PKT_LEN < seq:
                return None

            f.seek(TINYSSB_PKT_LEN * (seq-1))
            buf = f.read(TINYSSB_PKT_LEN)
            return buf if len(buf) == TINYSSB_PKT_LEN else None

    def feed_read_chunk(self, fid: bytes, seq: int, cnr: int) -> Optional[bytes]:
        try:
            with self._open_file(fid, "rb", seq, 0) as f:
                f.seek(TINYSSB_PKT_LEN * cnr)
                buf = f.read(TINYSSB_PKT_LEN)
                return buf if len(buf) == TINYSSB_PKT_LEN else None
        except FileNotFoundError:
            return None
        
    def feed_read_content(self, fid: bytes, seq: int) -> tuple[Optional[bytes], Optional[bytes]]:
        logEntry = self.feed_read_pkt(fid, seq)
        if logEntry is None:
            return (None, None)
        mid = self.feed_read_mid(fid, seq)
        if mid is None:
            return (None, None)
        if logEntry[DMX_LEN] == PKTTYPE_plain48:
            return (logEntry[DMX_LEN + 1: DMX_LEN+1+48], mid)
        if logEntry[DMX_LEN] != PKTTYPE_chain20:
            return (None, None)
        (sz, length) = bipf.varint_decode_max(logEntry, DMX_LEN + 1, DMX_LEN + 4)
        if sz <= 28 - length:
            return (logEntry[DMX_LEN+1+length: DMX_LEN+1+length+sz], mid)
        
        content = logEntry[DMX_LEN + 1+length: DMX_LEN+1+28]
        with self._open_file(fid, "rb", seq, 0) as sidechain:
            while True:
                buf = sidechain.read()
                if len(buf) != TINYSSB_PKT_LEN:
                    break
                content += buf[:TINYSSB_PKT_LEN - HASH_LEN]

        if len(content) < sz:
            return (None, None)
        if len(content) == sz:
            return (content, mid)
        return (content[:sz], mid)
        
    def feed_len(self, fid: bytes) -> int:
        f = os.path.join(os.path.join(self.FEED_DIR, fid.hex()), "log")
        return os.path.getsize(f) // TINYSSB_PKT_LEN
    
    def mk_content_log_entry(self, content: bytes) -> Optional[bytes]:
        fid = self.node.me
        frec = self.fid2rec(fid, False)
        if frec is None:
            return None
        sz_enc = bytearray(bipf.varint_encoding_length(len(content)))
        bipf.varint_encode(len(content), sz_enc)
        if len(sz_enc) + len(content) <= 28:
            intro = sz_enc + content + bytearray(28 - len(sz_enc) - len(content))
            ptr = bytearray(HASH_LEN)
        else:
            i = 28 - len(sz_enc)
            intro = sz_enc + content[:i]
            remaining = content[i:]
            chunks: list[bytes] = []
            ptr = bytearray(HASH_LEN)
            while remaining is not None:
                length = len(remaining) % 100
                if length == 0:
                    length = 100
                pkt = remaining[-length:]
                pkt += bytearray(100 - length) + ptr
                chunks.append(pkt)
                ptr = hashlib.sha256(pkt).digest()[:HASH_LEN]
                if length >= len(remaining):
                    remaining = None
                else:
                    remaining = remaining[:-len(remaining)]
            if len(chunks) > 0:
                chunks.reverse()
                with self._open_file(fid, "wb", frec.next_seq, 0) as chain:  
                    for b in chunks:
                        chain.write(b)
        nm0 = fid + frec.next_seq.to_bytes(4, "big") + frec.prev_hash
        dmx = GOset.compute_dmx(nm0)
        msg = dmx + util.PKTTYPE_chain20.to_bytes(1, "big") + intro + ptr
        return msg + self.node.ks.sign(fid, DMX_PFX + nm0 + msg)
    
    def feed_append(self, fid: bytes, pkt: bytes) -> bool:
        ndx = self._feed_index(fid)
        print("append ndx:", ndx)
        if ndx < 0:
            return False
        seq = self.feeds[ndx].next_seq
        print("append seq:", seq)
        nm0 = fid + seq.to_bytes(4, "big") + self.feeds[ndx].prev_hash
        dmx = GOset.compute_dmx(nm0)
        if pkt[:DMX_LEN] != dmx:
            print("repo: DMX mismatch")
            return False
        buf = DMX_PFX + nm0 + pkt
        if not self.node.ks.verify(fid, pkt[56:], buf[:-64]):
            print("repo: signature verification failed")
            return False
        
        with self._open_file(fid, "ab") as f:
            f.write(pkt)
        h = hashlib.sha256(pkt[:HASH_LEN]).digest()
        self.feeds[ndx].prev_hash = h
        if self.feeds[ndx].next_seq >= 1:
            with self._open_file(fid, "ab", 1) as f:
                f.write(h)
        d = os.path.join(self.FEED_DIR, fid.hex())
        if self.feeds[ndx].next_seq >= 2:
            try:
                os.remove(os.path.join(d,f"+{self.feeds[ndx].next_seq - 1}"))
            except:
                pass
        self.feeds[ndx].next_seq += 1

        if pkt[DMX_LEN] == PKTTYPE_plain48:
            e = LogTinyEntry(fid, seq, h, pkt[DMX_LEN + 1: DMX_LEN + 1 +48])
            self.node.on_tiny_event(e)
        if pkt[DMX_LEN] == PKTTYPE_chain20:
            sz, length = bipf.varint_decode_max(pkt, DMX_LEN + 1, DMX_LEN + 4)
            print("DEBUG")
            if sz <= 28 - length:
                content = pkt[DMX_LEN + 1 + length: DMX_LEN + 1 + length + sz]
                e = LogTinyEntry(fid, seq, h, content)
                print("test")
                self.node.on_tiny_event(e)
            else:
                if os.path.exists(os.path.join(d, f"-{seq}")):
                    content, mid = self.feed_read_content(fid, seq)
                    if content is not None and mid is not None:
                        e = LogTinyEntry(fid, seq, mid, content)
                        self.node.on_tiny_event(e)
                        
                else:
                    with open(os.path.join(d, f"!{seq}"), "w+"):
                        pass
        self.node.arm_dmx(pkt[:DMX_LEN]) # remove old dmx 
        new_dmx = GOset.compute_dmx(fid + self.feeds[ndx].next_seq.to_bytes(4, "big") 
                                    + self.feeds[ndx].prev_hash)
        self.node.arm_dmx(new_dmx, lambda buf, fid: self.node.incoming_pkt(buf, fid), fid)
        return True


    def sidechain_append(self, buf: bytes, chunk_indx: int) -> None:
        print("sidechain_append()")
        b = self.node.blbt[chunk_indx]

        with self._open_file(b.fid, "ab", b.seq, 1) as f:
            f.write(buf)
        i = TINYSSB_PKT_LEN - HASH_LEN - 1
        while i < TINYSSB_PKT_LEN:
            if buf[i] != 0:
                break
            i += 1
        if i == TINYSSB_PKT_LEN:
            fdir = os.path.join(self.FEED_DIR, b.fid.hex())
            os.rename(os.path.join(fdir, f'!{b.seq}'), os.path.join(fdir, f'-{b.seq}'))
            content, mid = self.feed_read_content(b.fid, b.seq)
            if content is not None and mid is not None:
                e = LogTinyEntry(b.fid, b.seq, mid, content)
                self.node.on_tiny_event(e)
        else:
            h = buf[TINYSSB_PKT_LEN - HASH_LEN:]
            self.node.arm_blob(h, lambda chunk, b_ndx: self.node.incoming_chainedblob(chunk, b_ndx), b.fid, b.seq, b.bnr + 1)
        self.node.arm_blob(b.h)

    # def listFeeds(self) -> list[bytes]:
    #     pass
