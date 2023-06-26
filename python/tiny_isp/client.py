
import os
from typing import Optional
from tinyssb.goset import GOset, GOsetManager
from tinyssb.repo import LogTinyEntry
from tinyssb.util import atomic_write, DATA_FOLDER
from .feed_pub import FeedPub
from .protocol import Tiny_ISP_Protocol
from tinyssb.keystore import Keystore
import hashlib
import base64
import bipf

STATE_ONBOARDING = "onboarding"
STATE_ESTABLISHED = "established"
STATE_FAREWELL = "farewell"
STATE_TERMINATED = "terminated"



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

        self.subscriptions = {}
        self.supended_state = {}


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

    def on_ctrl_add_key(self, key: bytes) -> None:
        print("on_add_key ISP")
        print("ISP CTRL_GO ADDED: ", key.hex())
        self.isp.feed_pub.subscribe(key, self.on_ctrl_rx)

    def on_data_add_key(self, key: bytes) -> None:
        print("ISP DATA_GO ADDED")
        self.isp.feed_pub.subscribe(key, self.on_data_rx)

    def on_data_rx(self, event: LogTinyEntry) -> None:
        print("on_datarx: received", bipf.loads(event.body))
        fid = event.fid
        mid = event.mid
        cmd, args = Tiny_ISP_Protocol.from_bipf(event.body)

        if fid != self.client_data_feed:
            return
        
        if cmd is None:
            return
        
        match cmd:
            case Tiny_ISP_Protocol.TYPE_DATA_FEEDHOPPING_PREV:
                print("Feedhopping_prev at", event.seq)
                if event.seq != 1:
                    raise Exception("Feedhopping prev message not at seqNo 0")


                if self.client_prev_data_feed != args[0]:
                    raise Exception("Feedhopping prev pointer of new feed is not matching next pointer of previos feed")
                
            case Tiny_ISP_Protocol.TYPE_DATA_FEEDHOPPING_NEXT:
                if event.seq != Tiny_ISP_Protocol.DATA_FEED_MAX_ENTRIES:
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
        print("publish over data len:", self.isp.node.repo.feed_len(self.isp_data_feeds[0]))
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
            'suspended_state': self.supended_state
        }
        with atomic_write(path, binary=True) as f:
            f.write(bipf.dumps(data))

    def load(self, data):
        self.status = data['status']
        self.isp_ctrl_feed =  data['isp_ctrl_feed']
        self.ctrl_goset._add_key(self.isp_ctrl_feed)
        self.ctrl_goset.adjust_state()
        self.isp_data_feeds = data['isp_data_feeds']
        self.client_data_feed = data['client_data_feed']
        self.client_prev_data_feed = data['client_prev_data_feed']
        if data['data_goset_epoch'] != 0:
            self.data_goset.set_epoch(data['data_goset_epoch'])
        if self.isp_data_feeds is not None:
            self.data_goset._add_key(self.isp_data_feeds[0])
        self.data_goset._add_key(self.client_data_feed)
        self.subscriptions = data['subscriptions']
        self.supended_state = data['suspended_state']
        self.data_goset.adjust_state()

    @staticmethod
    def load_from_file(isp, contractID_str: str) -> 'Client':
        with open(os.path.join(isp.ISP_DIR, contractID_str), 'rb') as f:
            data = bipf.loads(f.read())
        cl = Client(isp, data['client_id'], data['contract_id'], data['client_ctrl_feed'], data)
        return cl
