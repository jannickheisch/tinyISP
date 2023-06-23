
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
        self.status = STATE_ONBOARDING

        self.isp_ctrl_feed = None

        self.data_goset = self.go_set_manager.add_goset("data" + client_id.hex() + contract_id.hex(), 0, self.on_data_add_key)
        self.client_data_feeds: list[bytes] = []
        self.isp_data_feeds: list[bytes] = []


        # load if called from load_from_file() all stored information
        if loaded_information:
            ##self.load(loaded_information)
            return

        # otherwise we need to create a new isp->Client ctrl feed and notify the client
        self.isp_ctrl_feed = self.isp.create_new_feed()
        self.ctrl_goset._add_key(self.isp_ctrl_feed)
        self.ctrl_goset.adjust_state()

        #self.dump()

    def on_ctrl_add_key(self, key: bytes) -> None:
        print("on_add_key ISP")
        print("ISP CTRL ADDED: ", key.hex())
        self.isp.feed_pub.subscribe(key, self.on_ctrl_rx)

    def on_data_add_key(self, key: bytes) -> None:
        print("ISP DATA ADDED")
        self.isp.feed_pub.subscribe(key, self.on_data_rx)

    def on_data_rx(self, event: LogTinyEntry) -> None:
        pass

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
    
    def create_data_feed(self) -> bytes:
        id = self.isp.create_new_feed()
        self.isp_data_feeds.append(id)
        self.data_goset._add_key(id)
        self.data_goset.adjust_state()
        return id

    def on_onboard_ack(self, data_feed: bytes):
        self.client_data_feeds.append(data_feed)
        self.data_goset._add_key(data_feed)
        self.data_goset.adjust_state()

        self.send_over_ctrl(Tiny_ISP_Protocol.onboard_ack(self.create_data_feed()))
        self.status = STATE_ESTABLISHED

    def send_over_ctrl(self, content: bytes):
        self.isp.node.publish_public_content(content, self.isp_ctrl_feed)

    def _persist(self) -> None:
        self.dump(os.path.join(self.isp.ISP_DIR, self.contract_id.hex()))


    def dump(self, path: str) -> None:
        data = {
            'client_id': self.client_id,
            'contract_id': self.contract_id,
            'client_ctrl_feed': self.client_ctrl_feed,
            'status': self.status,
            'isp_ctrl_feed': self.isp_ctrl_feed,
            'self.client_data_feeds': self.client_data_feeds,
            'self.isp_data_feeds': self.isp_data_feeds,
            'data_goset_epoch': self.data_goset.epoch
        }
        with atomic_write(path, binary=True) as f:
            f.write(bipf.dumps(data))

    def load(self, data):
        self.status = data['status']
        self.isp_ctrl_feed =  data['isp_ctrl_feed']
        self.isp_data_feeds = data['self.isp_data_feeds']
        if data['data_goset_epoch'] != 0:
            self.data_goset.set_epoch(data['data_goset_epoch'])

    @staticmethod
    def load_from_file(isp, contractID_str: str) -> 'Client':
        with open(os.path.join(isp.ISP_DIR, contractID_str), 'rb') as f:
            data = bipf.decode(f.read())
        cl = Client(isp, data['client_id'], data['contract_id'], data['client_ctrl_feed'], data)
        return cl
