
from typing import Optional
from tinyssb.goset import GOset, GOsetManager
from tinyssb.repo import LogTinyEntry
from .feed_pub import FeedPub
from .protocol import Tiny_ISP_Protocol
import hashlib

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

        self.isp_ctr_feed = None
        self.client_data_feeds: list[bytes] = []
        self.isp_data_feeds: list[bytes] = []

        self.subscriptions: list[bytes] = []

        if loaded_information:
            self.load(loaded_information)
        # data and control feeds
        
        

        
        self.go_sets: list[GOset] = []

        self.contract_Status = None

    def load(self, data: dict) -> None:
        pass

    def on_rx(self, event: LogTinyEntry) -> None:
        fid = event.fid
        mid = event.mid
        cmd, args = Tiny_ISP_Protocol.from_bipf(event.body)

        if cmd is None:
            return
        
        match cmd:
            case "":
                pass

    def add_isp_control_feed(self, feed_id: bytes) -> bool:
        if self.go_sets[-1]._include_key(feed_id):
            self.isp_ctr_feed = feed_id
            return True
        return False
        
    def add_client_data_feed(self, feed_id: bytes) -> bool:
        if self.go_sets[-1]._include_key(feed_id):
            self.client_data_feeds.append(feed_id)
            return True
        return False

    def add_isp_data_feed(self, feed_id: bytes) -> bool:
        if self.go_sets[-1]._include_key(feed_id):
            self.isp_data_feeds.append(feed_id)
            return True
        return False

    def save_to_file(self, path: str) -> None:
        pass
    
    @staticmethod
    def load_from_file(path: str) -> 'Client':
        client_id = bytes()
        contract_id = bytes()
        client_ctrl = bytes()
        return Client(client_id, contract_id, client_ctrl)


