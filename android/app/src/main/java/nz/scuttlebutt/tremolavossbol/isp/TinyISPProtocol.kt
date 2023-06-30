package nz.scuttlebutt.tremolavossbol.isp

import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.Bipf_e
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_APP_ISP
import java.security.cert.CertPathValidatorException.BasicReason


class TinyISPProtocol {
    companion object{
        // Onboarding
        const val TYPE_ANNOUNCEMENT = "announcement" // Announces that this node is an ISP
        const val TYPE_ONBOARDING_REQUEST = "onboard_request" // A client initiates an onboarding, already containing a control_feed Client -> ISP
        const val TYPE_ONBOARDING_RESPONSE = "onboard_response" // The ISP notifies the client if the onboarding was successful, and sends his control feed ISP -> CLient
        const val TYPE_ONBOARDING_ACK = "onboard_ack" // The node acknowledges a successful onboarding and starts any further communication over the control feeds (indicates that this ctrl_feed is active)


        // Data feed management
        const val TYPE_DATA_FEEDHOPPING_PREV = "feedhopping_prev"
        const val TYPE_DATA_FEEDHOPPING_NEXT = "feedhopping_next"
        const val TYPE_DATA_FEED_FIN = "feedhopping_fin" //  confirmation, that the feed hopping was successful and the old feed can now be deleted.

        const val DATA_FEED_MAX_ENTRIES = 50


        // Subscribing
        const val TYPE_SUBSCRIPTION_REQUEST = "sub_req" // Request a Subscription. This request is forwarded by the ip to the requested client.
        const val TYPE_SUBSCRIPTION_ISP_REQUEST = "sub_req_isp" // This is the forwarded message of the ISP
        const val TYPE_SUBSCRIPTION_RESPONSE = "sub_resp" // Response to the request. This response if forwarded by the isp to the requesting client.
        const val TYPE_SUBSCRIPTION_ISP_RESPONSE = "sub_resp_isp" // This is the forwarded response, or a response of the ISP

        const val REASON_NOT_FOUND = "not_found" // the request was denied, because the requested client is not a client of this ISP
        const val REASON_REJECTED = "rejected" // the request was denied, because the requested client didn't accept the request


        // Farewell
        const val TYPE_FAREWELL_INITIATE = "farewell_init" // notifies the other side that the contract is going to be terminated, the sending node only replicates the data that is in the data feed, but doesn't append new entries to it
        const val TYPE_FAREWELL_ACK = "farewell_ack" // response to farewell_init, confirms the start of the farewell-phase and also stops appending new entries to the data feed
        const val TYPE_FAREWELL_FIN = "farewell_fin" // notifies the other side, that the sending node has successfully read all the data and that it is ready to terminate the contract


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

        fun data_feed_next(next: ByteArray?): ByteArray {
            return _to_bipf(TYPE_DATA_FEEDHOPPING_NEXT, listOf(next))
        }

        fun data_feed_fin(fid: ByteArray): ByteArray {
            return _to_bipf(TYPE_DATA_FEED_FIN, listOf(fid))
        }

        fun subscription_request(subscribe_to_id: ByteArray, c2cFid: ByteArray): ByteArray {
            return _to_bipf(TYPE_SUBSCRIPTION_REQUEST, listOf(subscribe_to_id, c2cFid))
        }

        fun forwarded_subscription_request(ref: ByteArray, from_fid: ByteArray, c2c_fid: ByteArray): ByteArray {
            return _to_bipf(TYPE_SUBSCRIPTION_ISP_REQUEST, listOf(ref, from_fid, c2c_fid))
        }

        fun subscription_response(ref: ByteArray, accepted: Boolean, c2c_fid: ByteArray?): ByteArray {
            if(accepted && c2c_fid == null)
                throw Exception("Subscription is accepted, but no c2c-data-feed is given")
            return _to_bipf(TYPE_SUBSCRIPTION_RESPONSE, listOf(ref, accepted, c2c_fid))
        }

        fun forwarded_subscription_response(ref: ByteArray, accepted: Boolean, c2c_fid: ByteArray?, reason: String? = null): ByteArray {
            if(accepted && c2c_fid == null)
                throw Exception("Subscription is accepted, but no c2c-data-feed is given")
            if(!accepted && reason == null)
                throw Exception("The subscription was not accepted, but no reason is given")
            return _to_bipf(TYPE_SUBSCRIPTION_ISP_RESPONSE, listOf(ref, accepted, c2c_fid ?: reason))
        }

        fun farewell_init(): ByteArray {
            return _to_bipf(TYPE_FAREWELL_INITIATE)
        }

        fun farewell_ack(): ByteArray {
            return _to_bipf(TYPE_FAREWELL_ACK)
        }

        fun farewell_fin(): ByteArray {
            return _to_bipf(TYPE_FAREWELL_FIN)
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
