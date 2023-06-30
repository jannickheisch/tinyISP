
from typing import Optional, Any
import bipf


class Tiny_ISP_Protocol:
    """
    This class specifies the various tinyISP commands with their arguments.
    
    It also serves as an interface by describing all available commands through methods that encode and return the given command in BIPF format.
    """

    # States of a Client-ISP-Contract

    # Onboarding
    TYPE_ANNOUNCEMENT = "announcement" # Announces that this node is an ISP
    TYPE_ONBOARDING_REQUEST = "onboard_request" # A client initiates an onboarding, already containing a control_feed Client -> ISP
    TYPE_ONBOARDING_RESPONSE = "onboard_response" # The ISP notifies the client if the onboarding was successful, and sends his control feed ISP -> CLient
    TYPE_ONBOARDING_ACK = "onboard_ack" # The node acknowledges a successful onboarding and starts any further communication over the control feeds (indicates that this ctrl_feed is active)
    
    # Data feed

    TYPE_DATA_FEEDHOPPING_PREV = "feedhopping_prev" # At the beginning of each datafeed, points to the previous data feed. None if it is the first data feed
    TYPE_DATA_FEEDHOPPING_NEXT = "feedhopping_next" # At the end of each data feed, points to the next data feed for feed hopping. None if this is the last send data feed
    TYPE_DATA_FEED_FIN = "feedhopping_fin" # Confirmation, that the feed hopping was successful and that the previous feed can now be safely deleted. Implicitly removes the previous data feed ID from the data goset and increases the epoch of the data goset
    
    DATA_FEED_MAX_ENTRIES = 50 # including prev and next message
    
    # Subscribing
    TYPE_SUBSCRIPTION_REQUEST = "sub_req" # Request a Subscription. This request is forwarded by the ip to the requested client.
    TYPE_SUBSCRIPTION_ISP_REQUEST = "sub_req_isp" # This is the forwarded message of the ISP
    TYPE_SUBSCRIPTION_RESPONSE = "sub_resp" # Response to the request. This response if forwarded by the isp to the requesting client.
    TYPE_SUBSCRIPTION_ISP_RESPONSE = "sub_resp_isp" # This is the forwarded response, or a response of the ISP

    REASON_NOT_FOUND = "not_found" # the request was denied, because the requested client is not a client of this ISP
    REASON_REJECTED = "rejected" # the request was denied, because the requested client didn't accept the request

    # Farewell
    TYPE_FAREWELL_INITIATE = "farewell_init" # notifies the other side that the contract is going to be terminated, the sending node only replicates the data that is in the data feed, but doesn't append new entries to it
    TYPE_FAREWELL_ACK = "farewell_ack" # response to farewell_init, confirms the start of the farewell-phase and also stops appending new entries to the data feed
    TYPE_FAREWELL_FIN = "farewell_fin" # notifies the other side, that the sending node has successfully read all the data and that it is ready to terminate the contract


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
    def data_feed_next(next: Optional[bytes]) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_DATA_FEEDHOPPING_NEXT, [next])

    @staticmethod
    def data_feed_fin(feed_id: bytes) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_DATA_FEED_FIN, [feed_id])
    
    @staticmethod
    def subscription_request(subscribe_to_fid: bytes, c2c_fid: bytes) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_SUBSCRIPTION_REQUEST,  [subscribe_to_fid, c2c_fid])
    
    @staticmethod
    def forwarded_subscription_request(ref: bytes, from_fid: bytes, c2c_fid: bytes) -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_SUBSCRIPTION_ISP_REQUEST, [ref, from_fid, c2c_fid])
    
    @staticmethod
    def subscription_response(ref: bytes, accepted: bool, c2c_fid: Optional[bytearray]) -> bytes:
        if accepted and c2c_fid is None:
            raise Exception("Subscription is accepted, but no c2c-data-feed is given")
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_SUBSCRIPTION_RESPONSE, [ref, accepted, c2c_fid])
    
    @staticmethod
    def forwarded_subscription_response(ref: bytes, accepted: bool, c2c_fid: Optional[bytearray], reason: Optional[str] = None) -> bytes:
        if accepted and c2c_fid is None:
            print("Forwarded subscription is accepted, but no c2c-data-feed is given")
            raise Exception("Forwarded subscription is accepted, but no c2c-data-feed is given")
        if not accepted and reason is None:
            print("The subscription was not accepted, but no reason is given")
            raise Exception("The subscription was not accepted, but no reason is given")
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_SUBSCRIPTION_ISP_RESPONSE, [ref, accepted, c2c_fid if c2c_fid is not None else reason])
    
    @staticmethod
    def farewell_init() -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_FAREWELL_INITIATE)
    
    @staticmethod
    def farewell_ack() -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_FAREWELL_ACK)
    
    @staticmethod
    def farewell_fin() -> bytes:
        return Tiny_ISP_Protocol._to_bipf(Tiny_ISP_Protocol.TYPE_FAREWELL_FIN)


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
