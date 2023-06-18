import json
import os
import shutil
import sys
import time

import bipf
from tinyssb import keystore, util, repo, node, io
import tinyssb as tiny

import base64

class Chatapp:

    def __init__ (self,name: str):

        if (name == "reset"):
            shutil.rmtree(util.DATA_FOLDER, ignore_errors=True)
            return

        pfx = util.DATA_FOLDER + name
        if( not os.path.exists(pfx + '/_backed/config.json')):
            os.makedirs(f'{pfx}/_backed')

            ks = keystore.Keystore()
            self.pk = ks.new(name)

            ks.dump(pfx + '/_backed/' + util.hex(self.pk))

            with open(f"{pfx}/_backed/config.json", "w") as f:
                f.write(util.json_pp({'name': name, 'rootFeedID': util.hex(self.pk), 'id': f'@{base64.b64encode(self.pk).decode()}.ed25519'}))
            
            #repo.mk_generic_log(self.pk, packet.PKTTYPE_plain48, b'log entry 1', lambda msg: ks.sign(self.pk, msg))
        else:
            with open(pfx + '/_backed/config.json') as f:
                cfg = json.load(f)
            self.pk = util.fromhex(cfg['rootFeedID'])
            ks = keystore.Keystore()
            ks.load(pfx + '/_backed/' + cfg['rootFeedID'])

        faces = [io.UDP_MULTICAST(('239.5.5.8', 1558))]
        self.node = node.NODE(faces, ks, self.pk, self.newEvent)

        print("id:", f'@{base64.b64encode(self.pk).decode()}.ed25519')

        # for log in self.node.repo.listlog():
        #     self.node.repo.get_log(log).set_append_cb(self.newEvent)

        self.node.start()
        self.loop()


    def backend(self, data):
        data = bipf.dumps(data)
        self.node.publish_public_content(data)

    def newEvent(self, pkt: repo.LogTinyEntry):
        print("NEW CHAT:")
        if pkt is not None:
            print(bipf.loads(pkt.body))
        else:
            print("received null")

    def loop(self): #9cf59d63d66ba33d98d6a5bd083716ea14e59e23700852a2ddae78081f7a3b09
        while True:
            inp = input(">")
            if (inp.lower() == "/exit"):
                break
            if inp.startswith("/long"):
                message = ["TAV", "Das ist eine Nachricht die so lange ist, dass sie in mehreren Blobs versendet werden muss", None, int(time.time()/1000)]
                self.backend(message)
                continue
            message = ["TAV", inp, None, int(time.time())]
            self.backend(message)

if __name__ == '__main__':
    Chatapp(sys.argv[1])
    # Chatapp("Bob")
