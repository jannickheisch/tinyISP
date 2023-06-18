import json
import os
import shutil
import sys
import time
import base64
import bipf
from tinyssb import keystore, util, repository, packet, node, io
import tinyssb as tiny


class ISP:
    ALIAS = "ISP"

    def __init__(self) -> None:
        pfx = util.DATA_FOLDER + self.ALIAS
        if( not os.path.exists(pfx + '/_backed/config.json')):
            os.makedirs(f'{pfx}/_blob')
            os.makedirs(f'{pfx}/_logs')
            os.makedirs(f'{pfx}/_backed')

            ks = keystore.Keystore()
            self.pk = ks.new(self.ALIAS)

            ks.dump(pfx + '/_backed/' + util.hex(self.pk))

            with open(f"{pfx}/_backed/config.json", "w") as f:
                f.write(util.json_pp({'name': self.ALIAS, 'rootFeedID': util.hex(self.pk), 'id': f'@{base64.b64encode(self.pk).decode()}.ed25519'}))
        pass

    def reset(self) -> None:
        shutil.rmtree(util.DATA_FOLDER, ignore_errors=True)
