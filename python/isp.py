import json
import os
import shutil
import sys
import time
import base64
import bipf
from tinyssb import keystore, util, node, io, goset, repo
from tiny_isp.client import Client
from tiny_isp.feed_pub import FeedPub
import tinyssb as tiny
from contextlib import contextmanager
from tiny_isp.protocol import Tiny_ISP_Protocol

from typing import Any, Optional, Callable, Generator, Type



class FeedManager:

    def __init__(self) -> None:
        self.go_set = []
        self.control_feed_isp_client = None
        self.control_feed_client_isp = None
        self.data_feed_isp_client = []
        self.curr_data_feed_isp_client = None
        self.data_feed_client_isp = []
        self.curr_data_feed_isp_client = None

    def send_control_command(self):
        pass

class ISP:
    ALIAS = "ISP"

    def __init__(self) -> None:
        self.ISP_DIR = os.path.join(os.path.join(util.DATA_FOLDER, self.ALIAS), "isp")
        self.feed_pub = FeedPub()
        self.node = self.node_setup()
        self.go_set_manager = self.node.goset_manager
        self.whitelist: list[bytes] = []
        self.node.start()
        self.clients: list[Client] = []

        self.node.goset.adjust_state()
        self.node.goset.add_key_callback(self.on_add_key)

        for k in self.node.goset.keys:
            self.feed_pub.subscribe(k, self.on_tiny_event)
        


        # for log in self.node.repo.listlog():
        #     self.node.repo.get_log(log).set_append_cb(self.newEvent)

        self.node.start()
        self.loop()

    def on_add_key(self, key: bytes) -> None:
        self.feed_pub.subscribe(key, self.on_tiny_event)

    def node_setup(self) -> node.NODE:
        os.makedirs(self.ISP_DIR, exist_ok=True)

        pfx = util.DATA_FOLDER + self.ALIAS
        if( not os.path.exists(pfx + '/_backed/config.json')):
            os.makedirs(f'{pfx}/_backed')

            ks = keystore.Keystore()
            self.pk = ks.new(self.ALIAS)

            ks.dump(pfx + '/_backed/' + util.hex(self.pk))

            with open(f"{pfx}/_backed/config.json", "w") as f:
                f.write(util.json_pp({'name': self.ALIAS, 'rootFeedID': util.hex(self.pk),
                                      'id': f'@{base64.b64encode(self.pk).decode()}.ed25519'}))

        else:
            with open(pfx + '/_backed/config.json') as f:
                cfg = json.load(f)
            self.pk = util.fromhex(cfg['rootFeedID'])
            ks = keystore.Keystore()
            ks.load(pfx + '/_backed/' + cfg['rootFeedID'])

        print("id:", f'@{base64.b64encode(self.pk).decode()}.ed25519')

        faces = [io.UDP_MULTICAST(('239.5.5.8', 1558))]
        return node.NODE(faces, ks, self.pk, self.feed_pub.on_rx)

    def isp_setup(self) -> None:
        pass

    # only subscribed to listen to root feeds of other peers (global)
    def on_tiny_event(self, event: repo.LogTinyEntry) -> None:
        fid = event.fid
        cmd, args = Tiny_ISP_Protocol.from_bipf(event.body)

        match cmd:
            case Tiny_ISP_Protocol.TYPE_ONBOARDING_REQUEST:
                if args is None or len(args) != 1:
                    return
                self.on_onboarding_request(fid, event.mid, args[0])

    def on_onboarding_request(self, fid: bytes, contract_id: bytes, client_ctr_feed: bytes) -> None:
        if self.whitelist and fid not in self.whitelist:
            return

        if [c for c in self.clients if c.client_id]:
            return

        cl = Client(fid, contract_id, client_ctr_feed)
        self.clients.append(cl)

    def reset(self) -> None:
        shutil.rmtree(util.DATA_FOLDER)

@contextmanager
def atomic_write(path, binary = False) -> Generator[Type[FileExistsError], Any, None]:

    tmp = f'{path}.tmp'
    while os.path.exists(tmp):
        tmp += '.tmp'

    try:
        with open(tmp, 'w+b' if binary else 'w+'):
            yield FileExistsError
        os.rename(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except:
            pass
