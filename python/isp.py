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
from tiny_isp.protocol import Tiny_ISP_Protocol

from typing import Any, Optional, Callable, Generator, Type

import qrcode



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
        self.clients: list[Client] = []
        
        # self.node.goset.set_add_key_callback(self.on_add_key)

        self.feed_pub.subscribe(self.node.me, self.on_tiny_event)



        for contract in os.listdir(self.ISP_DIR):
            cl = Client.load_from_file(self, contract)
            self.clients.append(cl)

        # test_goset = self.node.goset_manager.add_goset("test")
        # test_goset._add_key(self.create_new_feed())
        # test_goset._add_key(self.create_new_feed())
        # test_goset.adjust_state()

        # for k in self.node.goset.keys:
        #     self.feed_pub.subscribe(k, self.on_tiny_event)


        # for log in self.node.repo.listlog():
        #     self.node.repo.get_log(log).set_append_cb(self.newEvent)

        self.node.start()
        # self.node.publish_public_content(bipf.dumps(["TAV", "Das ist eine Nachricht die so lange ist, dass sie in mehreren Blobs versendet werden muss", None, int(time.time()/1000)]))
        # self.announce()
        self.loop()

    def create_new_feed(self, alias: Optional[str] = None) -> bytes:
        fid = self.node.ks.new(alias)
        self.node.repo.new_feed(fid, repo.FEED_TYPE_ISP_VIRTUAL)
        self.node.ks.dump(util.DATA_FOLDER + self.ALIAS + '/_backed/' + self.node.me.hex())
        return fid


    def on_add_key(self, key: bytes) -> None:
        print("on_add_key")
        print("ADDED: ", key.hex())
        self.feed_pub.subscribe(key, self.on_tiny_event)

    def announce(self) -> None:
        self.node.publish_public_content(Tiny_ISP_Protocol.announce_isp())

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
        return node.NODE(self, faces, ks, self.pk, self.feed_pub.on_rx)

    def isp_setup(self) -> None:
        pass

    # only subscribed to listen to root feeds of other peers (global)
    def on_tiny_event(self, event: repo.LogTinyEntry) -> None:
        print("tiny_event_received:", bipf.loads(event.body), "mid", event.mid.hex())
        fid = event.fid
        cmd, args = Tiny_ISP_Protocol.from_bipf(event.body)



        print("cmd:", cmd, "args:", args)

        match cmd:
            case Tiny_ISP_Protocol.TYPE_ONBOARDING_REQUEST:
                if args is None or len(args) != 2:
                    return
                self.on_onboarding_request(event.mid, fid, event.mid, args[1])

    def on_onboarding_request(self, ref:bytes, fid: bytes,
                              contract_id: bytes, client_ctr_feed: bytes) -> None:
        print("received onboarding request")
        if self.whitelist and fid not in self.whitelist:
            print("Client not in whitelist")
            self.node.publish_public_content(Tiny_ISP_Protocol.onbord_response(ref, False))
            return
        print([c for c in self.clients if c.client_id])
        if [c for c in self.clients if c.client_id]:
            print("Client has already an active contract!")
            self.node.publish_public_content(Tiny_ISP_Protocol.onbord_response(ref, False))
            return
        
        print("create Client")

        cl = Client(self, fid, contract_id, client_ctr_feed)
        self.node.publish_public_content(
            Tiny_ISP_Protocol.onbord_response(ref, True, cl.isp_ctrl_feed))
        self.clients.append(cl)

    def loop(self):
        while True:
            inp = input(">>")
            if inp.lower() == "/me":
                my_id = f"@{base64.b64encode(self.node.me).decode('utf-8')}.ed25519"
                print(f"ID:", my_id)
                qr = qrcode.QRCode(version=1, box_size=10, border=4)
                qr.add_data(my_id)
                qr.make(fit=True)
                qr.print_tty()
            if inp.lower().startswith("/follow"):
                cmd_split = inp.split(" ")
                if len(cmd_split) != 2:
                    print("wrong arguments")
                    continue
                if not (cmd_split[1].startswith("@") and cmd_split[1].endswith("=.ed25519")):
                    print("SSB ids need to have the following format: @...=.ed25519")
                    continue
                fid = base64.b64decode(cmd_split[1][1:-8])
                self.node.repo.new_feed(fid, repo.FEED_TYPE_ROOT)
                go = self.node.goset_manager.add_goset(add_key_callback= lambda key: self.feed_pub.subscribe(key, self.on_tiny_event))
                go._add_key(fid)
                go._add_key(self.node.me)
                go.adjust_state()
            if inp.lower() == "/test":
                cl = self.clients[0]
                lst = ["Test", "TEst", "Test"]
                cl.publish_over_data(bipf.dumps(lst))

            time.sleep(0.2)

    def reset(self) -> None:
        shutil.rmtree(util.DATA_FOLDER)

if __name__ == "__main__":
    i = ISP()