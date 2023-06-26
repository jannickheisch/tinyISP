
from typing import Optional, Any
import bipf


class Tiny_ISP_Protocol:
    """
    This class specifies the various tinyISP commands with their arguments.
    
    It also serves as an interface by describing all available commands through methods that encode and return the given command in BIPF format.
    """

    # States of a Client-ISP-Contract

    # Onboarding
    TYPE_ANNOUNCEMENT = "announcement" # Announce that this node is an ISP
    TYPE_ONBOARDING_REQUEST = "onboard_request" # A client initiates an onboarding, already containing a control_feed Client -> ISP
    TYPE_ONBOARDING_RESPONSE = "onboard_response" # The ISP notifies the client if the onboarding was successful, and sends his control feed ISP -> CLient
    TYPE_ONBOARDING_ACK = "onboard_ack" # The node acknowledges a successful onboarding and starts any further communication over the control feeds (indicates that this ctrl_feed is active)
    
    # Data feed

    TYPE_DATA_FEEDHOPPING_PREV = "feedhopping_prev" # At the beginning of each datafeed, points to the previous data feed. None if it is the first data feed
    TYPE_DATA_FEEDHOPPING_NEXT = "feedhopping_next" # At the end of each data feed, points to the next data feed for feed hopping. None if this is the last send data feed

    TYPE_DATA_FEED_FIN = "feedhopping_fin" # Confirmation, that the feed hopping was successful and that the previous feed can now be safely deleted. Implicitly removes the previous data feed ID from the data goset and increases the epoch of the data goset
    DATA_FEED_MAX_ENTRIES = 4 # including prev and next message
    
    # Subscribing
    TYPE_SUBSCRIPTION_Request = "" # Request a Subscription. This request is forwarded by the ip to the requested client.
    TYPE_SUBSCRIPTION_Response = "" # Response to the request. Also forwared by the isp to the requesting client.

    TYPE_SUBSCRIPTION_UNSUBSCRIBE = ""
    TYPE_SUBSCRIPTION_UNSUBSCRIBE_ACK = ""

    # Farewell
    TYPE_FAREWELL_INITIATE = ""
    TYPE_FAREWELL_INITIATE_ACK = ""
    TYPE_FAREWELL_FINISHED = ""
    TYPE_FAREWELL_TERMINATED = ""
    
    # Misc


    @staticmethod
    def announce_isp() -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_ANNOUNCEMENT)
    
    @staticmethod
    def request_onboarding(target: bytes, ctrl_feed: bytes) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_ONBOARDING_REQUEST, [target, ctrl_feed])

    @staticmethod
    def onbord_response(ref: bytes, accepted: bool, ctrl_feed: Optional[bytes] = None) -> bytes:
        if accepted and ctrl_feed is None:
            raise MissingControlFeedException("Onboard request accepted, but no control feed is provided")
        args = []
        args.append(ref)
        args.append(accepted)
        args.append(ctrl_feed)
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_ONBOARDING_RESPONSE, args)

    @staticmethod
    def onboard_ack(data_feed: bytes) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_ONBOARDING_ACK, [data_feed])

    @staticmethod
    def data_feed_prev(prev: Optional[bytes]) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_DATA_FEEDHOPPING_PREV, [prev])

    @staticmethod
    def data_feed_next(next: bytes) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_DATA_FEEDHOPPING_NEXT, [next])

    @staticmethod
    def data_feed_fin(feed_id: bytes) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_DATA_FEED_FIN, [feed_id])
    
    @staticmethod
    def subscription_request(feed_id: bytes) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_SUBSCRIPTION_Request,  [feed_id])



    @staticmethod
    def _to_bipf(typ: str, args: Optional[list[Any]] = None) -> bytes:
        msg = []
        msg.append('ISP')
        msg.append(typ)
        if args is not None:
            msg.extend(args)
        return bipf.dumps(msg)

    @staticmethod
    def from_bipf(buf: bytes) -> tuple[Optional[str], Optional[list[Any]]]:
        payload = []
        try:
            payload = bipf.loads(buf)
        except:
            return (None , None)

        if payload is None or len(payload) < 2 or payload[0] != "ISP":
            return (None, None)

        if len(payload) == 2:
            return (payload[1], None)

        if len(payload) > 2:
            return (payload[1], payload[2:])

        return (None, None)



class MissingControlFeedException(Exception):
    def __init__(self, message):
        self.message = message
