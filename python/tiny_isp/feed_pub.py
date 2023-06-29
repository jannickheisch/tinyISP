from typing import Callable, Any
from tinyssb import repo
import bipf


class FeedPub:

    def __init__(self) -> None:
        self.subscriptions: dict[bytes, list[Callable]] = {}

    def subscribe(self, fid: bytes, callback: Callable[[repo.LogTinyEntry], Any]) -> None:
        print("subscribed: ", fid.hex())
        if fid in self.subscriptions and callback not in self.subscriptions[fid]:
            self.subscriptions[fid].append(callback)
        else:
            self.subscriptions[fid] = [callback]

    def unsubscribe(self, fid: bytes, callback: Callable[[repo.LogTinyEntry], None]) -> None:
        if callback in self.subscriptions[fid]:
            self.subscriptions[fid].remove(callback)

    def on_rx(self, entry: repo.LogTinyEntry) -> None:
        print("feedpub received")
        try:
            print("feedpub received:", bipf.loads(entry.body))
        except:
            pass
        fid = entry.fid
        if fid in self.subscriptions:
            for c in self.subscriptions[fid]:
                c(entry)
