
import os
import time
from typing import Optional
from tinyssb.goset import GOset, GOsetManager
from tinyssb.repo import LogTinyEntry, FEED_TYPE_ISP_VIRTUAL
from tinyssb.util import atomic_write, DATA_FOLDER, TINYSSB_PKT_LEN, DMX_LEN
from .feed_pub import FeedPub
from .protocol import Tiny_ISP_Protocol
from tinyssb.keystore import Keystore
import hashlib
import base64
import bipf

STATE_ONBOARDING = "onboarding"
STATE_ESTABLISHED = "established"
STATE_FAREWELL = "farewell"
STATE_FAREWELL_FIN = "farewell_fin"


class Client:
    """
    This class represents a tinyISP client.

    It includes all the methods and information necessary to 
    provide the client with the services specified in the contract.
    """

    def __init__(self, isp, client_id: bytes, contract_id: bytes, client_ctrl: bytes, loaded_information: Optional[dict] = None) -> None:
        self.isp = isp

        self.go_set_manager: GOsetManager = isp.go_set_manager
        self.feed_pub: FeedPub = isp.feed_pub
        
        self.ctrl_goset = self.go_set_manager.add_goset("ctrl" + client_id.hex() + contract_id.hex(), 0)
        self.ctrl_goset.set_add_key_callback(self.on_ctrl_add_key)
        print("CLient ctrl:", client_ctrl.hex())
        self.ctrl_goset._add_key(client_ctrl)
        self.ctrl_goset.adjust_state()

        self.client_id = client_id
        self.contract_id = contract_id
        self.client_ctrl_feed = client_ctrl
        
        self.isp_ctrl_feed = None

        self.data_goset = self.go_set_manager.add_goset("data" + client_id.hex() + contract_id.hex(), 0, self.on_data_add_key)
        self.client_data_feed: Optional[bytes] = None
        self.client_prev_data_feed: Optional[bytes] = None
        self.isp_data_feeds: list[bytes] = []

        self.pendingSubs: dict[bytes, bytes] = {} # ref -> c2c_feed
        self.subscriptions = {}
        self.supended_state = {}
        self.replication_state = {}

        self.buffer = {} # dmx -> pkt

        self.farewell_fin_received = False


        # load if called from load_from_file() all stored information
        if loaded_information:
            self.load(loaded_information)
            return

        # otherwise we need to create a new isp->Client ctrl feed and notify the client
        self.isp_ctrl_feed = self.isp.create_new_feed()
        print("created isp CTRL:", self.isp_ctrl_feed)
        self.ctrl_goset._add_key(self.isp_ctrl_feed)
        self.ctrl_goset.adjust_state()
        self.status = STATE_ONBOARDING
        self._persist()

        #self.dump()

    def sendToRepo(self, buf: bytes):
        pkt_dmx = buf[:DMX_LEN]

        if self.isp.node.dmxt_find(pkt_dmx) is None:
            print("dmx not found -> send to buffer")
            print("dmx: " + pkt_dmx.hex())
            self.buffer[pkt_dmx] = buf
            self._persist()
            return
        
        print("send to rx handler with len", len(buf))
        for i in range(0, len(buf), TINYSSB_PKT_LEN):
            print("send slice", i)
            curr_slice = buf[i: i+TINYSSB_PKT_LEN]
            self.isp.node.on_rx(curr_slice, None)

        next_pkt_dmx = None
        for pending in self.buffer:
            if self.isp.node.dmxt_find(pending) is not None:
                next_pkt_dmx = pending
                break

        if next_pkt_dmx is not None:
            wire = self.buffer[next_pkt_dmx]
            del self.buffer[next_pkt_dmx]
            self.sendToRepo(wire)
        
        self._persist()



    def on_ctrl_add_key(self, key: bytes) -> None:
        print("on_add_key ISP")
        print("ISP CTRL_GO ADDED: ", key.hex())
        self.isp.feed_pub.subscribe(key, self.on_ctrl_rx)

    def on_data_add_key(self, key: bytes) -> None:
        print("ISP DATA_GO ADDED")
        self.isp.feed_pub.subscribe(key, self.on_data_rx)

    def on_data_rx(self, event: LogTinyEntry) -> None:
        try:
            print("on_datarx: received", bipf.loads(event.body))
        except:
            print("on_datarx: received no decodable")
            pass
        fid = event.fid
        mid = event.mid
        try:
            cmd, args = Tiny_ISP_Protocol.from_bipf(event.body)
        except:
            cmd, args = (None, None)

        if fid != self.client_data_feed:
            return
        
        if cmd is None:
            if len(event.body) % TINYSSB_PKT_LEN == 0:
                print("on_data_rx received tunneled log entry")
                self.sendToRepo(event.body)
            else:
                print("on data rx, tunneled data size not matching")

        
        match cmd:
            case Tiny_ISP_Protocol.TYPE_DATA_FEEDHOPPING_PREV:
                print("Feedhopping_prev at", event.seq)
                if event.seq != 1:
                    raise Exception("Feedhopping prev message not at seqNo 0")


                if self.client_prev_data_feed != args[0]:
                    raise Exception("Feedhopping prev pointer of new feed is not matching next pointer of previos feed")
                
            case Tiny_ISP_Protocol.TYPE_DATA_FEEDHOPPING_NEXT:
                if event.seq != Tiny_ISP_Protocol.DATA_FEED_MAX_ENTRIES:
                    next = args[0]
                    if next is None:
                        self.isp.feed_pub.unsubscribe(self.client_data_feed, self.on_data_rx)
                        self.publish_over_ctrl(Tiny_ISP_Protocol.farewell_fin())
                        self.status = STATE_FAREWELL_FIN
                        self._persist()
                        if (self.status == STATE_FAREWELL_FIN and self.farewell_fin_received):
                            self.terminate()
                        return
                    else:
                        raise Exception(f"Feedhopping next message is not at end of feed, seq = {event.seq}")
                
                self.client_prev_data_feed = self.client_data_feed
                self.client_data_feed = args[0]
                self.isp.feed_pub.unsubscribe(self.client_prev_data_feed, self.on_data_rx)
                self.data_goset.remove_key(self.client_prev_data_feed)
                self.data_goset._add_key(self.client_data_feed)
                self.data_goset.adjust_state()
                self.publish_over_ctrl(Tiny_ISP_Protocol.data_feed_fin(self.client_prev_data_feed))
                self._persist()
                self.isp.node.repo.remove_feed(self.client_prev_data_feed) # the old data feed is no longer needed

    def on_ctrl_rx(self, event: LogTinyEntry) -> None:
        fid = event.fid
        mid = event.mid
        cmd, args = Tiny_ISP_Protocol.from_bipf(event.body)

        print("on_ctrl_rx: cmd:", cmd, args)

        if fid != self.client_ctrl_feed: # only allow control commands over ctrl feeds
            return

        if cmd is None:
            return

        match cmd:
            case Tiny_ISP_Protocol.TYPE_ONBOARDING_ACK:
                self.on_onboard_ack(args[0])
            case Tiny_ISP_Protocol.TYPE_DATA_FEED_FIN:
                if args[0] != self.isp_data_feeds[0]:
                    raise Exception("Client sended fin message for invalid data feed")
                self.data_goset.remove_key(args[0])
                self.data_goset._add_key(self.isp_data_feeds[1])
                self.data_goset.adjust_state()
                # client confirmed successfull feedhopp -> remove old data feed
                self.isp_data_feeds = self.isp_data_feeds[1:]
                self.isp.node.repo.remove_feed(args[0])
                self._persist()
                if self.supended_state:
                    self.resume()
            case Tiny_ISP_Protocol.TYPE_SUBSCRIPTION_REQUEST:
                cl = next((cl for cl in self.isp.clients if cl.client_id == args[0]), None)
                if cl is None:
                    print("could not find client for sub request")
                    self.publish_over_ctrl(Tiny_ISP_Protocol.forwarded_subscription_response(event.mid, False, None, Tiny_ISP_Protocol.REASON_NOT_FOUND))
                    return
                self.pendingSubs[event.mid] = args[1]
                self.isp.ref_to_client[event.mid] = self
                cl.publish_over_ctrl(Tiny_ISP_Protocol.forwarded_subscription_request(event.mid, self.client_id, args[1]))
                self._persist()
            case Tiny_ISP_Protocol.TYPE_SUBSCRIPTION_RESPONSE:
                if not args[0] in self.isp.ref_to_client:
                    print("Response ref not found")
                    return
                cl: Client = self.isp.ref_to_client[args[0]]
                if args[1]:
                    cl.publish_over_ctrl(Tiny_ISP_Protocol.forwarded_subscription_response(args[0], True, args[2]))
                    del self.isp.ref_to_client[args[0]]
                    cl.subscriptions[self.client_id] = [cl.pendingSubs[args[0]], args[2]]
                    self.subscriptions[cl.client_id] = [args[2], cl.pendingSubs[args[0]]]
                    self.isp.node.repo.new_feed(cl.pendingSubs[args[0]], FEED_TYPE_ISP_VIRTUAL)
                    self.isp.node.repo.new_feed(args[2], FEED_TYPE_ISP_VIRTUAL)
                    self.arm_pkt_dmx(cl.pendingSubs[args[0]])
                    self.arm_pkt_dmx(args[2])
                    self.feed_pub.subscribe(self.subscriptions[cl.client_id][0], lambda entry: cl.publish_over_data(self.isp.node.repo.feed_read_pkt_wire(entry.fid, entry.seq)))
                    self.feed_pub.subscribe(self.subscriptions[cl.client_id][1], lambda entry: self.publish_over_data(self.isp.node.repo.feed_read_pkt_wire(entry.fid, entry.seq)))
                    del cl.pendingSubs[args[0]]
                else:
                    cl.publish_over_ctrl(Tiny_ISP_Protocol.forwarded_subscription_response(args[0], False, None, Tiny_ISP_Protocol.REASON_REJECTED))
                    del self.isp.ref_to_client[args[0]]
                    del cl.pendingSubs[args[0]]
                self._persist()
            case Tiny_ISP_Protocol.TYPE_FAREWELL_INITIATE:
                if self.status == STATE_ESTABLISHED: # otherwise this node already initiated a farewell
                    self.publish_over_data(Tiny_ISP_Protocol.data_feed_next(None))
                    self.status = STATE_FAREWELL
                    self.publish_over_ctrl(Tiny_ISP_Protocol.farewell_ack())
                    self.status = STATE_FAREWELL
                    self._persist()
            case Tiny_ISP_Protocol.TYPE_FAREWELL_FIN:
                self.farewell_fin_received = True
                self._persist()
                if self.status == STATE_FAREWELL_FIN and self.farewell_fin_received:
                    self.terminate()

    def arm_pkt_dmx(self, fid: bytes):
        frec = self.isp.node.repo.fid2rec(fid, True, FEED_TYPE_ISP_VIRTUAL)
        dmx = self.ctrl_goset.compute_dmx(fid + frec.next_seq.to_bytes(4, 'big') + frec.prev_hash)
        print("arm_pkt_dmx, fid: ", fid.hex(), frec.next_seq, frec.prev_hash, dmx.hex())
        self.isp.node.arm_dmx(dmx, lambda buf, fid: self.isp.node.incoming_pkt(buf, fid), fid)

                
    
    def create_data_feed(self, prev: Optional[bytes]) -> bytes:
        id = self.isp.create_new_feed()
        print("created data feed:", id.hex())
        self.isp_data_feeds.append(id)
        if prev is None:
            self.data_goset._add_key(id)
            self.data_goset.adjust_state()
        self.publish_over_data(Tiny_ISP_Protocol.data_feed_prev(prev))
        self._persist()
        return id

    def on_onboard_ack(self, data_feed: bytes):
        if (self.status != STATE_ONBOARDING):
            return
        print("Onboarding: received client datafeed:", data_feed.hex())
        self.client_data_feed = data_feed
        self.data_goset._add_key(data_feed)
        self.data_goset.adjust_state()

        self.publish_over_ctrl(Tiny_ISP_Protocol.onboard_ack(self.create_data_feed(None)))
        self.status = STATE_ESTABLISHED
        self._persist()

    def publish_over_ctrl(self, content: bytes):
        self.isp.node.publish_public_content(content, self.isp_ctrl_feed)

    def publish_over_data(self, content: bytes):
        self.isp.node.publish_public_content(content, self.isp_data_feeds[0])
        print("publish over data feed len:", self.isp.node.repo.feed_len(self.isp_data_feeds[0]))
        print("content len:", len(content))
        if self.isp.node.repo.feed_len(self.isp_data_feeds[0]) == Tiny_ISP_Protocol.DATA_FEED_MAX_ENTRIES - 1:
            if len(self.isp_data_feeds) == 3:
                self.suspend()
                return
            print("feed hop")
            old = self.isp_data_feeds[0]
            new = self.create_data_feed(old)
            self.isp.node.publish_public_content(Tiny_ISP_Protocol.data_feed_next(new), old)

    # Flow control
    def suspend(self):
        for fid in self.subscriptions.values():
            size = self.isp.node.repo.feed_len(fid)
            self.supended_state[fid] = size
        self._persist()

    def resume(self):
        pass

    def start_farewell(self):
        self.publish_over_ctrl(Tiny_ISP_Protocol.farewell_init())
        self.publish_over_data(Tiny_ISP_Protocol.data_feed_next(None))
        self.status = STATE_FAREWELL
        self._persist()

    def terminate(self):
        time.sleep(10)
        self.go_set_manager.remove_goset(self.data_goset)
        self.go_set_manager.remove_goset(self.ctrl_goset)

        self.isp.clients.remove(self)
        self.feed_pub.unsubscribe_from_all(self.client_ctrl_feed)
        self.isp.node.repo.remove_feed(self.client_ctrl_feed)

        self.feed_pub.unsubscribe_from_all(self.isp_ctrl_feed)
        self.isp.node.repo.remove_feed(self.isp_ctrl_feed)

        self.feed_pub.unsubscribe_from_all(self.client_data_feed)
        self.isp.node.repo.remove_feed(self.client_data_feed)

        for fid in self.isp_data_feeds:
            self.feed_pub.unsubscribe_from_all(fid)
            self.isp.node.repo.remove_feed(fid)

        # c2c feeds are not removed
        try:
            os.remove(os.path.join(self.isp.ISP_DIR, self.contract_id.hex()))
        except:
            pass

    
    def _persist(self) -> None:
        self.dump(os.path.join(self.isp.ISP_DIR, self.contract_id.hex()))

    def dump(self, path: str) -> None:
        data = {
            'client_id': self.client_id,
            'contract_id': self.contract_id,
            'client_ctrl_feed': self.client_ctrl_feed,
            'status': self.status,
            'isp_ctrl_feed': self.isp_ctrl_feed,
            'client_data_feed': self.client_data_feed,
            'client_prev_data_feed': self.client_prev_data_feed,
            'isp_data_feeds': self.isp_data_feeds,
            'data_goset_epoch': self.data_goset.epoch,
            'subscriptions': self.subscriptions,
            'pendingSubs': self.pendingSubs,
            'suspended_state': self.supended_state,
            'buffer': self.buffer,
            'farewell_fin_received': self.farewell_fin_received
        }
        with atomic_write(path, binary=True) as f:
            f.write(bipf.dumps(data))

    def load(self, data):
        self.status = data['status']
        self.farewell_fin_received = data['farewell_fin_received']
        self.isp_ctrl_feed =  data['isp_ctrl_feed']
        self.ctrl_goset._add_key(self.isp_ctrl_feed)
        self.ctrl_goset.adjust_state()
        self.isp_data_feeds = data['isp_data_feeds']
        self.client_data_feed = data['client_data_feed']
        self.client_prev_data_feed = data['client_prev_data_feed']
        if data['data_goset_epoch'] != 0:
            self.data_goset.set_epoch(data['data_goset_epoch'])
        if self.isp_data_feeds:
            self.data_goset._add_key(self.isp_data_feeds[0])
        if self.client_data_feed:
            self.data_goset._add_key(self.client_data_feed)
        self.data_goset.adjust_state()
        self.subscriptions = data['subscriptions']
        self.supended_state = data['suspended_state']
        self.pendingSubs = data['pendingSubs']
        self.buffer = data['buffer']
        for sub in self.subscriptions.keys():
            self.arm_pkt_dmx(self.subscriptions[sub][0])
            self.arm_pkt_dmx(self.subscriptions[sub][1])
            self.feed_pub.subscribe(self.subscriptions[sub][1], lambda entry: self.publish_over_data(self.isp.node.repo.feed_read_pkt_wire(entry.fid, entry.seq)))
        self.data_goset.adjust_state()

    @staticmethod
    def load_from_file(isp, contractID_str: str) -> 'Client':
        with open(os.path.join(isp.ISP_DIR, contractID_str), 'rb') as f:
            data = bipf.loads(f.read())
        cl = Client(isp, data['client_id'], data['contract_id'], data['client_ctrl_feed'], data)
        return cl
