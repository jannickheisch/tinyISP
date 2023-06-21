
from typing import Optional
from tinyssb.goset import GOset, GOsetManager
from tinyssb.repo import LogTinyEntry
from tinyssb.util import atomic_write
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
        
        self.ctrl_goset = self.go_set_manager.add_goset("ctrl" + client_id.hex() + contract_id.hex(), 0)
        self.ctrl_goset._add_key(client_ctrl)
        self.feed_pub: FeedPub = isp.feed_pub
        self.feed_pub.subscribe(client_ctrl, self.on_rx)
        self.ctrl_goset.adjust_state()

        self.client_id = client_id
        self.contract_id = contract_id
        self.client_ctrl_feed = client_ctrl
        self.status = STATE_ONBOARDING

        self.isp_ctrl_feed = None

        self.data_goset: Optional[GOset] = None

        # load if called from load_from_file() all stored information
        if loaded_information:
            ##self.load(loaded_information)
            return

        # otherwise we need to create a new isp->Client ctrl feed and notify the client
        self.isp_ctrl_feed = self.isp.create_new_feed()
        self.ctrl_goset._add_key(self.isp_ctrl_feed)
        self.ctrl_goset.adjust_state()

        #self.dump()

    def on_rx(self, event: LogTinyEntry) -> None:
        fid = event.fid
        mid = event.mid
        cmd, args = Tiny_ISP_Protocol.from_bipf(event.body)

        if cmd is None:
            return

        match cmd:
            case Tiny_ISP_Protocol.TYPE_ONBOARDING_ACK:
                pass

    # def add_isp_control_feed(self, feed_id: bytes) -> bool:
    #     if self.go_sets[-1]._include_key(feed_id):
    #         self.isp_ctrl_feed = feed_id
    #         return True
    #     return False
        
    # def add_client_data_feed(self, feed_id: bytes) -> bool:
    #     if self.go_sets[-1]._include_key(feed_id):
    #         self.client_data_feeds.append(feed_id)
    #         return True
    #     return False

    # def add_isp_data_feed(self, feed_id: bytes) -> bool:
    #     if self.go_sets[-1]._include_key(feed_id):
    #         self.isp_data_feeds.append(feed_id)
    #         return True
    #     return False

    def dump(self, path: str) -> None:
        data = {
            'client_id': self.client_id,
            'contract_id': self.contract_id,
            'client_ctrl_feed': self.client_ctrl_feed,
            'isp_ctrl_feed': self.isp_ctrl_feed,
            'data_goset_epoch': self.data_goset.epoch,
            'data_goset_keys': self.data_goset.keys,
            'status': self.status
        }
        with atomic_write(path, binary=True) as f:
            f.write(bipf.dumps(data))

    @staticmethod
    def load(isp, path: str) -> 'Client':
        with open(path, 'rb') as f:
            data = bipf.decode(f.read())
        cl = Client(isp, data['client_id'], data['contract_id'], data['client_ctrl_feed'])
        return cl
