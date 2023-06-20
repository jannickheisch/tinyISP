from typing import Callable, Any
from tinyssb import repo


class FeedPub:

    def __init__(self) -> None:
        self.subscriptions: dict[bytes, list[Callable]] = {}

    def subscribe(self, fid: bytes, callback: Callable[[repo.LogTinyEntry], Any]) -> None:
        if fid in self.subscriptions:
            self.subscriptions[fid].append(callback)
        else:
            self.subscriptions[fid] = [callback]

    def unsubscribe(self, fid: bytes, callback: Callable[[repo.LogTinyEntry], None]) -> None:
        if callback in self.subscriptions[fid]:
            self.subscriptions[fid].remove(callback)

    def on_rx(self, entry: repo.LogTinyEntry) -> None:
        fid = entry.fid
        if fid in self.subscriptions:
            for c in self.subscriptions[fid]:
                c(entry)
