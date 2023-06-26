package nz.scuttlebutt.tremolavossbol.isp

import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.Bipf_e
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_APP_ISP


class TinyISPProtocol {
    companion object{
        // Onboarding
        const val TYPE_ANNOUNCEMENT = "announcement" // Announce that this node is an ISP
        const val TYPE_ONBOARDING_REQUEST = "onboard_request" // A client initiates an onboarding, already containing a control_feed Client -> ISP
        const val TYPE_ONBOARDING_RESPONSE = "onboard_response" // The ISP notifies the client if the onboarding was successful, and sends his control feed ISP -> CLient
        const val TYPE_ONBOARDING_ACK = "onboard_ack" // The node acknowledges a successful onboarding and starts any further communication over the control feeds (indicates that this ctrl_feed is active)

        // Data feed management
        const val TYPE_DATA_FEEDHOPPING_PREV = "feedhopping_prev"
        const val TYPE_DATA_FEEDHOPPING_NEXT = "feedhopping_next"
        const val TYPE_DATA_FEED_FIN = "feedhopping_fin"

        const val DATA_FEED_MAX_ENTRIES = 4

        const val TYPE_DATA_FEED_HOPPING_INITIATE = "" // initiates Feed hopping to a new feed
        const val TYPE_DATA_FEED_HOPPING_ACK = "" // the other party acknowledges the feed Hopping and indicates that it will listen to the new feed
        const val TYPE_DATA_FEED_HOPPING_FIN = "" //  confirmation, that the feed hopping was successful and the old feed can now be deleted.

        // Subscribing
        const val TYPE_SUBSCRIPTION_SUBSCRIBE = ""
        const val TYPE_SUBSCRIPTION_SUBSCRIBE_ACK = ""

        const val TYPE_SUBSCRIPTION_UNSUBSCRIBE = ""
        const val TYPE_SUBSCRIPTION_UNSUBSCRIBE_ACK = ""

        // Goset Management
        const val TYPE_GOSET_REMOVE_KEY = ""
        const val TYPE_GOSET_REMOVE_KEY_ACK = ""

        // Farewell
        const val TYPE_FAREWELL_INITIATE = ""
        const val TYPE_FAREWELL_ACK = ""
        const val TYPE_FAREWELL_FINISHED = ""
        const val TYPE_FAREWELL_TERMINATED = ""

        fun announce_isp(): ByteArray {
            return _to_bipf(TYPE_ANNOUNCEMENT)
        }

        fun request_onboarding(target: ByteArray, ctrl_feed: ByteArray):ByteArray {
            return _to_bipf(TYPE_ONBOARDING_REQUEST, listOf(target, ctrl_feed))
        }

        fun onbord_response(ref: ByteArray, accepted: Boolean, ctrl_feed: ByteArray? = null): ByteArray {
            if (accepted && ctrl_feed == null)
                throw java.lang.Exception("Onboard request accepted, but no control feed is provided")

            if (accepted)
                return _to_bipf(TYPE_ONBOARDING_RESPONSE, listOf(ref, true, ctrl_feed!!))

            return _to_bipf(TYPE_ONBOARDING_RESPONSE, listOf(ref, false))
        }

        fun onboard_ack(data_feed: ByteArray): ByteArray {
            return _to_bipf(TYPE_ONBOARDING_ACK, listOf(data_feed))
        }

        fun data_feed_prev(prev: ByteArray?): ByteArray {
            return _to_bipf(TYPE_DATA_FEEDHOPPING_PREV, listOf(prev))
        }

        fun data_feed_next(next: ByteArray): ByteArray {
            return _to_bipf(TYPE_DATA_FEEDHOPPING_NEXT, listOf(next))
        }

        fun data_feed_fin(fid: ByteArray): ByteArray {
            return _to_bipf(TYPE_DATA_FEED_FIN, listOf(fid))
        }

        private fun _to_bipf(typ: String, args: List<Any?>? = null): ByteArray {
            val lst = Bipf.mkList()
            Bipf.list_append(lst, TINYSSB_APP_ISP)
            Bipf.list_append(lst, Bipf.mkString(typ))
            if (args != null) {
                for (arg in args) {
                    val tmp = when (arg) {
                        is Int -> Bipf.mkInt(arg)
                        is String -> Bipf.mkString(arg)
                        is Boolean -> Bipf.mkBool(arg)
                        is ByteArray -> Bipf.mkBytes(arg)
                        null -> Bipf.mkNone()
                        else -> throw Exception("_to_bipf, unknown type")
                    }
                    Bipf.list_append(lst, tmp)
                }
            }
            return Bipf.encode(lst)!!

    }
}

}
    /*
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

    if payload is None:
    return (None, None)

    if len(payload) == 1:
    return (payload[0], None)

    if len(payload) > 1:
    return (payload[0], payload[1:])

    return (None, None)

    */