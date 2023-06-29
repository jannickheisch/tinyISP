package nz.scuttlebutt.tremolavossbol.isp

import android.content.Context
import android.util.AtomicFile
import android.util.Base64
import android.util.Log
import androidx.core.util.writeBytes
import nz.scuttlebutt.tremolavossbol.MainActivity
import nz.scuttlebutt.tremolavossbol.crypto.SodiumAPI.Companion.sha256
import nz.scuttlebutt.tremolavossbol.tssb.GOset
import nz.scuttlebutt.tremolavossbol.tssb.LogTinyEntry
import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.Bipf_e
import nz.scuttlebutt.tremolavossbol.utils.Constants
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.DMX_LEN
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.GOSET_DMX_STR
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_PKT_LEN
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.decodeHex
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toBase64
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toByteArray
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toHex
import java.io.File


const val STATE_ONBOARD_REQUESTED = "onboard_requested"
const val STATE_ONBOARD_ACK = "onboard_ack"
const val STATE_ESTABLISHED = "established"


class ISP {


    private var buffer: MutableMap<String, ByteArray>
    private var receivedRequests: MutableMap<String, Pair<ByteArray, ByteArray>>
    private var pendingSubRequests: MutableMap<String, ByteArray>
    private var subscriptions: MutableMap<String, ArrayList<ByteArray>>
    private var isp_prev_data_feed: ByteArray?
    private var data_goset: GOset
    private var isp_data_feed: ByteArray?
    private var client_data_feeds: ArrayList<ByteArray>
    private var context: MainActivity
    private var state: String
    private var ctrl_goset: GOset
    var contractID: ByteArray
    private var client_ctrl_feed: ByteArray
    private var isp_ctrl_feed: ByteArray?
    private var root_goset: GOset


    var ispID: ByteArray
    val ISP_DIR = "isp"

    constructor(context: MainActivity, ispID: ByteArray, client_ctrl_feed: ByteArray, contractID: ByteArray) {
        this.context = context
        this.ispID = ispID
        this.client_ctrl_feed = client_ctrl_feed
        this.contractID = contractID

        this.root_goset = context.gosetManager.add_goset(null, GOSET_DMX_STR, 0)
        context.feedPub.subscribe(ispID, { entry -> context.wai.sendTinyEventToFrontend(entry) })
        this.root_goset._add_key(context.idStore.identity.verifyKey)
        if (!context.tinyRepo.feed_exists(ispID))
            context.tinyRepo.new_feed(ispID, context.tinyRepo.FEED_TYPE_ROOT)
        this.root_goset._add_key(ispID)
        this.root_goset.adjust_state()

        val add_ctrl_key_callback = {key: ByteArray -> context.feedPub.subscribe(key, {entry: LogTinyEntry ->  on_ctrl_rx(entry) })}
        val ctrl_dmx = "ctrl" + context.idStore.identity.verifyKey.toHex() + contractID.toHex()
        this.ctrl_goset = context.gosetManager.add_goset(add_ctrl_key_callback, ctrl_dmx)
        this.ctrl_goset._add_key(client_ctrl_feed)
        this.ctrl_goset.adjust_state()

        val add_data_key_callback = {key: ByteArray -> context.feedPub.subscribe(key, {entry: LogTinyEntry ->  on_data_rx(entry) })}
        val data_dmx = "data" + context.idStore.identity.verifyKey.toHex() + contractID.toHex()
        this.data_goset =  context.gosetManager.add_goset(add_data_key_callback, data_dmx, 0)
        this.client_data_feeds = ArrayList<ByteArray>()
        this.isp_data_feed = null
        this.isp_prev_data_feed = null

        this.isp_ctrl_feed = null

        this.subscriptions = mutableMapOf<String, ArrayList<ByteArray>>() // rootFID.toHex(): [my_c2c_feed, other_c2c_feed]
        this.pendingSubRequests = mutableMapOf<String, ByteArray>() // ref: rootFID.toHex()

        this.buffer = mutableMapOf<String, ByteArray>() // dmx.toHex(): pkt_wire

        this.receivedRequests = mutableMapOf<String, Pair<ByteArray, ByteArray>>() // rootFID.toHex(): (ref, c2c_feed)

        this.state = STATE_ONBOARD_REQUESTED
        persist()
    }

    fun sendToRepo(buf: ByteArray) {
        Log.d("sendToRepo", "received len: ${buf.size}")
        val pkt_dmx = buf.sliceArray(0 until DMX_LEN)
        Log.d("sendToRepo", "received dmx: ${pkt_dmx}")
        if(context.tinyDemux.dmxt_find(pkt_dmx) == null) { // no handler --> some previous packets are missing
            Log.d("sendToRepo", "couldn't find matching handler, buffering...")
            buffer[pkt_dmx.toHex()] = buf
            return
        }

        for (i in 0 until buf.size step TINYSSB_PKT_LEN) {
            val curr_slice = buf.sliceArray(i until i + TINYSSB_PKT_LEN)
            context.tinyDemux.on_rx(curr_slice)
        }

        var next: String? = null
        for (pendingDMX in buffer) {
            if (context.tinyDemux.dmxt_find(pendingDMX.key.decodeHex()) != null) {
                next = pendingDMX.key
                break
            }
        }

        if (next != null) {
            val wire = buffer[next]
            buffer.remove(next)
            sendToRepo(wire!!)
        }
    }

    fun on_ctrl_rx(entry: LogTinyEntry) {
        Log.d("on ctrl feed", "received: ${bipf_to_arraylist(Bipf.decode(entry.body))}, from ${entry.fid.toHex()}, expected: ${isp_ctrl_feed?.toHex()}")
        Log.d("ISP", "received log entry")

        if(entry.fid.contentEquals(client_ctrl_feed)) {
            val lst = bipf_to_arraylist(Bipf.decode(entry.body))
            if (lst == null || lst.size < 3)
                return
            if(lst[0] == "ISP" && lst[1] == TinyISPProtocol.TYPE_SUBSCRIPTION_REQUEST) {
                pendingSubRequests[entry.mid.toHex()] = (lst[2] as ByteArray)
                persist()
            }
        }

        if (!entry.fid.contentEquals(isp_ctrl_feed))
            return

        val buf = Bipf.decode(entry.body)

        if (buf == null)
            return
        val lst = bipf_to_arraylist(buf)
        if (lst == null || lst.size < 2)
            return

        if (lst[0] != "ISP")
            return

        when(lst[1]) {
            TinyISPProtocol.TYPE_ONBOARDING_ACK -> on_onboard_ack(lst[2] as ByteArray)
            TinyISPProtocol.TYPE_DATA_FEED_FIN -> {
                val arg = (lst[2] as ByteArray)
                if (!arg.contentEquals(client_data_feeds[0]))
                    throw Exception("ISP sended fin message for invalid data feed")
                data_goset.removeKey(arg)
                data_goset._add_key(client_data_feeds[1])
                data_goset.adjust_state()
                // ISP confirmed successfull feedhopp -> remove old data feed
                client_data_feeds.removeFirst()
                persist()
            }
            TinyISPProtocol.TYPE_SUBSCRIPTION_ISP_REQUEST -> {
                val ref = lst[2] as ByteArray
                val from_fid = lst[3] as ByteArray
                val c2c_fid = lst[4] as ByteArray
                Log.d("on isp request", "received request from ${from_fid.toHex()}")
                receivedRequests[from_fid.toHex()] = Pair(ref, c2c_fid)
                context.wai.eval("b2f_received_subRequest(\"" + ispID.toBase64() +"\", \"" + from_fid.toBase64() + "\", \"" + ref.toBase64() + "\")")
            }
            TinyISPProtocol.TYPE_SUBSCRIPTION_ISP_RESPONSE -> {
                val ref = lst[2] as ByteArray
                val accepted = lst[3] as Boolean

                if(!pendingSubRequests.containsKey(ref.toHex())) {
                    Log.e("on_sub_response", "ref deoesn't match to any request")
                    return
                }

                if (accepted) {
                    val c2c_feed = lst[4] as ByteArray
                    val from_fid = pendingSubRequests[ref.toHex()]
                    subscriptions[from_fid!!.toHex()]!!.add(c2c_feed)
                    pendingSubRequests.remove(ref.toHex())
                    context.feedPub.subscribe(c2c_feed, { entry -> c2c_to_frontend(entry) })
                    context.tinyRepo.new_feed(subscriptions[from_fid.toHex()]!![0], context.tinyRepo.FEED_TYPE_ISP_VIRTUAL)
                    context.tinyRepo.new_feed(subscriptions[from_fid.toHex()]!![1], context.tinyRepo.FEED_TYPE_ISP_VIRTUAL)
                    arm_c2c_dmx(c2c_feed)
                    context.feedPub.subscribe(subscriptions[from_fid.toHex()]!![0], { entry -> c2c_to_frontend(entry) })
                    context.feedPub.subscribe(subscriptions[from_fid.toHex()]!![0], {entry -> sendOverData(context.tinyRepo.feed_read_pkt_wire(entry.fid, entry.seq)!!)})
                    Log.d("sub_response", "c2c for ${from_fid.toHex()} feeds: ${subscriptions[from_fid.toHex()]!![0].toHex()}, ${subscriptions[from_fid.toHex()]!![1].toHex()}")
                    persist()
                    context.wai.eval("b2f_received_subResponse(\"" + ispID.toBase64() + "\", \"" + from_fid.toBase64() + "\", true)")
                } else {
                    val from_fid = pendingSubRequests[ref.toHex()]
                    pendingSubRequests.remove(ref.toHex())
                    subscriptions.remove(from_fid!!.toHex())
                    context.wai.eval("b2f_received_subResponse(\"" + ispID.toBase64() + "\", \"" + from_fid.toBase64() + "\", false)")
                    persist()
                }
            }
        }
    }

    fun arm_c2c_dmx(c2c_fid: ByteArray) {
        Log.d("armC2Cdmx", "for ${c2c_fid.toHex()}")
        val frec = context.tinyRepo.fid2rec(c2c_fid)
        val dmx = context.tinyDemux.compute_dmx(
            c2c_fid + frec!!.next_seq.toByteArray()
                    + frec.prev_hash)
        val fct = { buf: ByteArray, fid: ByteArray?, _: String? ->
            context.tinyNode.incoming_pkt(
                buf,
                fid!!
            )
        }
        context.tinyDemux.arm_dmx(dmx, fct, c2c_fid)
        Log.d("armC2Cdmx", "armed: ${dmx.toHex()} for fid: ${c2c_fid.toHex()}")
    }

    fun on_data_rx(entry: LogTinyEntry) {
        Log.d("on data feed", "received: ${bipf_to_arraylist(Bipf.decode(entry.body))}, from ${entry.fid.toHex()}, expected: ${isp_data_feed?.toHex()}")

        if(!entry.fid.contentEquals(isp_data_feed))
            return

        val buf = Bipf.decode(entry.body)

        if (buf == null) {
            if(entry.body.size % TINYSSB_PKT_LEN == 0) {
                Log.d("on_data_rx", "received tunneld logentry")
                sendToRepo(entry.body)
            } else {
                Log.d("on_data_rx", "tunneled data size not matching")
            }
            return

        }

        val lst = bipf_to_arraylist(buf)
        if (lst == null || lst.size < 2)
            return

        if (lst[0] != "ISP")
            return
        Log.d("on data feed", "DEBUG")
        when(lst[1]) {
            TinyISPProtocol.TYPE_DATA_FEEDHOPPING_PREV -> {
                if (entry.seq != 1)
                    throw Exception("Feedhopping prev message not at the beginning of the data feed")
                if (!isp_prev_data_feed.contentEquals(lst[2] as ByteArray?))
                    throw Exception("Feedhopping prev pointer of new feed is not matching next pointer of previous feed")

            }
            TinyISPProtocol.TYPE_DATA_FEEDHOPPING_NEXT -> {
                Log.d("Feedhopping", "received next")
                if (entry.seq != TinyISPProtocol.DATA_FEED_MAX_ENTRIES)
                    throw Exception("Feedhopping next message is not at end of feed")

                isp_prev_data_feed = isp_data_feed
                isp_data_feed = lst[2] as ByteArray
                context.feedPub.unsubscribe(isp_data_feed!!, { entry: LogTinyEntry ->  on_ctrl_rx(entry) })
                data_goset.removeKey(isp_prev_data_feed!!)
                data_goset._add_key(isp_data_feed!!)
                data_goset.adjust_state()
                sendOverCtrl(TinyISPProtocol.data_feed_fin(isp_prev_data_feed!!))
                persist()
                context.tinyRepo.remove_feed(isp_prev_data_feed!!)
                Log.d("Feedhopping", "removed old feed")

            }
        }
    }

    fun c2c_to_frontend(entry: LogTinyEntry) {
        var rootFID: ByteArray? = null
        for (sub in subscriptions) {
            if (sub.value.size != 2)
                continue
            val my_c2c = sub.value[0]
            val other_c2c = sub.value[1]
            if (entry.fid.contentEquals(my_c2c)) {
                rootFID = context.idStore.identity.verifyKey
                break
            }
            if (entry.fid.contentEquals(other_c2c)) {
                rootFID = sub.key.decodeHex()
                break
            }
        }
        val modifiedEntry = LogTinyEntry(rootFID!!, entry.seq, entry.mid, entry.body)
        context.wai.sendTinyEventToFrontend(modifiedEntry)
    }

    fun subscribe(fid: ByteArray) {
        if (subscriptions.containsKey(fid.toHex()))
            return
        val c2c_fid = context.idStore.new().verifyKey
        subscriptions[fid.toHex()] = arrayListOf(c2c_fid)
        sendOverCtrl(TinyISPProtocol.subscription_request(fid, c2c_fid))
        persist()
    }

    fun respond_to_request(from_fid: ByteArray, accept: Boolean) {
        if (!receivedRequests.containsKey(from_fid.toHex())) {
            Log.e("Respond to request", "no request for fid: ${from_fid.toHex()}")
            return
        }
        if (accept) {
            val c2c_feed = context.idStore.new().verifyKey
            Log.d("response", "added c2c feeds: ${c2c_feed.toHex()}, ${receivedRequests[from_fid.toHex()]!!.second.toHex()}")
            context.tinyRepo.new_feed(c2c_feed, context.tinyRepo.FEED_TYPE_ISP_VIRTUAL)
            context.tinyRepo.new_feed(receivedRequests[from_fid.toHex()]!!.second, context.tinyRepo.FEED_TYPE_ISP_VIRTUAL)
            arm_c2c_dmx(receivedRequests[from_fid.toHex()]!!.second)
            context.feedPub.subscribe(receivedRequests[from_fid.toHex()]!!.second, { entry -> c2c_to_frontend(entry) })
            subscriptions[from_fid.toHex()] = arrayListOf(c2c_feed, receivedRequests[from_fid.toHex()]!!.second)
            sendOverCtrl(TinyISPProtocol.subscription_response(receivedRequests[from_fid.toHex()]!!.first, true, c2c_feed))
            receivedRequests.remove(from_fid.toHex())
            // TODO inform frontend
        } else {
            sendOverCtrl(TinyISPProtocol.subscription_response(receivedRequests[from_fid.toHex()]!!.first, false, null))
            receivedRequests.remove(from_fid.toHex())
        }
        persist()
    }

    fun isSubscribedTo(fid: ByteArray): Boolean {
        if (subscriptions.containsKey(fid.toHex())) {
            Log.d("isSubscribed?", "${fid.toHex()} not in list ${subscriptions.keys}")
            if(subscriptions[fid.toHex()]!!.size == 2)
                return true
        }
        return false
    }

    fun c2cSendTo(fid: ByteArray, buf: ByteArray): Boolean{
        if (subscriptions.containsKey(fid.toHex())) {
            if(subscriptions[fid.toHex()]!!.size == 2){
                val c2c_fid = subscriptions[fid.toHex()]!![0]
                val pkt = context.tinyRepo.mk_contentLogEntry(buf, c2c_fid)
                if (pkt == null) return false
                Log.d("c2cSendTo", "append c2c feed")
                context.tinyRepo.feed_append(c2c_fid, pkt)
                return true
            }
        }
        return false
    }


    fun on_onboard_ack(data_feed: ByteArray) {
        if (this.state != STATE_ONBOARD_ACK)
            return
        Log.d("on_onboard_ack", "added isp data feed: ${data_feed.toHex()}")
        isp_data_feed = data_feed
        data_goset._add_key(data_feed)
        data_goset.adjust_state()

        state = STATE_ESTABLISHED
        persist()
    }

    fun add_isp_ctrl_feed(feed_id: ByteArray) {
        if (isp_ctrl_feed != null)
            return

        ctrl_goset._add_key(feed_id)
        ctrl_goset.adjust_state()
        isp_ctrl_feed = feed_id
        this.state = STATE_ONBOARD_ACK
        send_onboard_ack()
        persist()
    }

    fun send_onboard_ack() {
        val fid = context.idStore.new().verifyKey
        client_data_feeds.add(fid)
        data_goset._add_key(fid)
        data_goset.adjust_state()
        val prevPkt = context.tinyRepo.mk_contentLogEntry(TinyISPProtocol.data_feed_prev(null), fid)
        context.tinyRepo.feed_append(fid, prevPkt!!)
        Log.d("send_onboard_ack()", "own data feed: ${fid.toHex()}")
        sendOverCtrl(TinyISPProtocol.onboard_ack(fid))
        persist()
    }

    fun sendOverCtrl(buf: ByteArray) {
        val pkt = context.tinyRepo.mk_contentLogEntry(buf, client_ctrl_feed)
        if (pkt == null) return
        context.tinyRepo.feed_append(client_ctrl_feed, pkt)
    }

    fun sendOverData(buf: ByteArray) {
        val pkt = context.tinyRepo.mk_contentLogEntry(buf, client_data_feeds.first())
        if (pkt == null) return
        context.tinyRepo.feed_append(client_data_feeds.first(), pkt)
        if (context.tinyRepo.feed_len(client_data_feeds.first()) == TinyISPProtocol.DATA_FEED_MAX_ENTRIES - 1) {
            if (client_data_feeds.size == 3) {
                suspend()
                return
            }
            val old = client_data_feeds.first()
            val new = context.idStore.new().verifyKey
            context.tinyRepo.new_feed(new, context.tinyRepo.FEED_TYPE_ISP_VIRTUAL)
            val nxtPkt = context.tinyRepo.mk_contentLogEntry(TinyISPProtocol.data_feed_next(new), old)
            if (nxtPkt == null) throw Exception("Error creating next pointer for new data feed")
            context.tinyRepo.feed_append(old, nxtPkt)
            val prevPkt = context.tinyRepo.mk_contentLogEntry(TinyISPProtocol.data_feed_prev(old), new)
            if (prevPkt == null) throw Exception("Error creating prev pointer for new data feed")
            context.tinyRepo.feed_append(new, prevPkt)
            client_data_feeds.add(new)
            persist()
        }
    }

    fun suspend() {

    }

    fun resume() {

    }



    fun delete() {
        context.tinyRepo.remove_feed(client_ctrl_feed)
        val f = File(File(context.getDir(Constants.TINYSSB_DIR, Context.MODE_PRIVATE), ISP_DIR), contractID.toHex())
        f.delete()
    }

    fun persist() {
        val buf = this.to_bipf()
        val f = AtomicFile(File(File(context.getDir(Constants.TINYSSB_DIR, Context.MODE_PRIVATE), ISP_DIR), contractID.toHex()))
        val outputStream = f.startWrite()
        outputStream.write(buf)
        outputStream.close()
        f.finishWrite(outputStream)
    }

    constructor(context: MainActivity, isp_id: ByteArray, contractID: ByteArray, client_ctrl_feed: ByteArray, state: String, isp_ctrl_feed: ByteArray?,
                client_data_feeds: ArrayList<ByteArray>?, isp_data_feed: ByteArray?, isp_prev_data_feed: ByteArray?, goset_epoch: Int, subscriptions: MutableMap<String, ArrayList<ByteArray>>,
                pendingSubRequests: MutableMap<String, ByteArray>, receivedRequests: MutableMap<String, Pair<ByteArray, ByteArray>>, buffer: MutableMap<String, ByteArray>
    ) {
        this.context = context
        this.ispID = isp_id
        this.contractID = contractID
        this.client_ctrl_feed = client_ctrl_feed
        this.state = state
        this.isp_ctrl_feed = isp_ctrl_feed
        this.client_data_feeds = if (client_data_feeds != null) client_data_feeds else ArrayList<ByteArray>()
        this.isp_data_feed = isp_data_feed
        this.isp_prev_data_feed = isp_prev_data_feed

        this.root_goset = context.gosetManager.add_goset(null, GOSET_DMX_STR, 0)
        context.feedPub.subscribe(ispID, { entry -> context.wai.sendTinyEventToFrontend(entry) })
        this.root_goset._add_key(context.idStore.identity.verifyKey)
        if (!context.tinyRepo.feed_exists(ispID))
            context.tinyRepo.new_feed(ispID, context.tinyRepo.FEED_TYPE_ROOT)
        this.root_goset._add_key(ispID)
        this.root_goset.adjust_state()

        val add_ctrl_key_callback = {key: ByteArray -> context.feedPub.subscribe(key, {entry: LogTinyEntry ->  on_ctrl_rx(entry) })}
        val ctrl_dmx = "ctrl" + context.idStore.identity.verifyKey.toHex() + contractID.toHex()
        this.ctrl_goset = context.gosetManager.add_goset(add_ctrl_key_callback, ctrl_dmx)
        this.ctrl_goset._add_key(client_ctrl_feed)
        if (isp_ctrl_feed != null)
            this.ctrl_goset._add_key(isp_ctrl_feed)
        this.ctrl_goset.adjust_state()

        this.subscriptions = subscriptions
        this.pendingSubRequests = pendingSubRequests
        this.receivedRequests = receivedRequests

        this.buffer = buffer

        for (sub in subscriptions) {
            if(sub.value.size == 2) {
                arm_c2c_dmx(sub.value[1])
                context.feedPub.subscribe(sub.value[1], { entry -> c2c_to_frontend(entry) })
                context.feedPub.subscribe(sub.value[0], { entry -> c2c_to_frontend(entry) })
                context.feedPub.subscribe(sub.value[0], { entry -> sendOverData(context.tinyRepo.feed_read_pkt_wire(entry.fid, entry.seq)!!)})
            }
        }


        val add_data_key_callback = {key: ByteArray -> context.feedPub.subscribe(key, {entry: LogTinyEntry ->  on_data_rx(entry) })}
        val data_dmx = "data" + context.idStore.identity.verifyKey.toHex() + contractID.toHex()
        this.data_goset =  context.gosetManager.add_goset(add_data_key_callback, data_dmx, goset_epoch)
        if (!client_data_feeds.isNullOrEmpty())
            this.data_goset._add_key(client_data_feeds[0])
        if (isp_data_feed != null)
            this.data_goset._add_key(isp_data_feed)
        this.data_goset.adjust_state()

    }

    companion object {
        fun load_from_file(context: MainActivity, file: File): ISP {
            val buf = file.readBytes()
            val data = bipf_to_arraylist(Bipf.bipf_loads(buf)!!)!!
            val isp_id = data[0] as ByteArray
            val contractID = data[1] as ByteArray
            val client_ctrl_feed = data[2] as ByteArray
            val state = data[3] as String
            val isp_ctrl_feed = data[4] as ByteArray?
            val client_data_feed = data[5] as ArrayList<ByteArray>?
            val isp_data_feed = data[6] as ByteArray?
            val isp_prev_data_feed = data[7] as ByteArray?
            val goset_epoch = data[8] as Int
            val subscriptions = mutableMapOf<String, ArrayList<ByteArray>>() // [rootFID.toHex()] = (my_c2c_feed, other_c2c_feed)
            for (sub in data[9] as ArrayList<ArrayList<*>>) {
                subscriptions[sub[0] as String] = ArrayList(sub.subList(1, sub.size)) as ArrayList<ByteArray>
            }
            Log.d("on_load", "loaded active subs with keys: ${subscriptions.keys}")
            val pendingSubRequests = mutableMapOf<String, ByteArray>() // [ref] = rootFID
            for (pending in data[10] as ArrayList<ArrayList<*>>) {
                pendingSubRequests[pending[0] as String] = pending[1] as ByteArray
            }
            val receivedRequests = mutableMapOf<String, Pair<ByteArray, ByteArray>>()
            for (recv in data[11] as ArrayList<ArrayList<*>>) {
                receivedRequests[recv[0] as String] = Pair(recv[1] as ByteArray, recv[2] as ByteArray)
            }
            Log.d("on_load", "loaded received Requests with keys: ${receivedRequests.keys}")

            val buffer = mutableMapOf<String, ByteArray>()
            for (buf in data[12] as ArrayList<ArrayList<*>>) {
                buffer[buf[0] as String] = buf[1] as ByteArray
            }

            return ISP(context, isp_id, contractID, client_ctrl_feed, state, isp_ctrl_feed, client_data_feed, isp_data_feed, isp_prev_data_feed, goset_epoch, subscriptions, pendingSubRequests, receivedRequests, buffer)
        }

        fun bipf_to_arraylist(buf: Bipf_e?): ArrayList<Any?>? {
            if (buf == null)
                return null
            if (!buf.isList())
                return null
            val list = buf.getList()
            val out = ArrayList<Any?>()
            for (e in list) {
                out.add(when(e.typ) {
                    Bipf.BIPF_LIST -> bipf_to_arraylist(e)
                    Bipf.BIPF_BYTES -> e.getBytes()
                    Bipf.BIPF_INT -> e.getInt()
                    Bipf.BIPF_STRING -> e.getString()
                    Bipf.BIPF_BOOLNONE -> {
                        if (e.v!!::class != Boolean::class)
                            null
                        else
                            e.getBoolean()
                    }
                    else -> throw Exception("bipf_to_arraylist unknown bipf type")
                })
            }
            return out
        }
    }

    private fun to_bipf(): ByteArray {
        val data = Bipf.mkList()
        Bipf.list_append(data, Bipf.mkBytes(ispID))
        Bipf.list_append(data, Bipf.mkBytes(contractID))
        Bipf.list_append(data, Bipf.mkBytes(client_ctrl_feed))
        Bipf.list_append(data, Bipf.mkString(state))

        if (isp_ctrl_feed == null)
            Bipf.list_append(data, Bipf.mkNone())
        else
            Bipf.list_append(data, Bipf.mkBytes(isp_ctrl_feed!!))

        if (client_data_feeds.isEmpty())
            Bipf.list_append(data, Bipf.mkNone())
        else {
            val tmp = Bipf.mkList()
            for (feed in client_data_feeds) {
                Bipf.list_append(tmp, Bipf.mkBytes(feed))
            }
            Bipf.list_append(data, tmp)
        }

        if(isp_data_feed == null)
            Bipf.list_append(data, Bipf.mkNone())
        else {
            Bipf.list_append(data, Bipf.mkBytes(isp_data_feed!!))
        }

        if (isp_prev_data_feed == null)
            Bipf.list_append(data, Bipf.mkNone())
        else
            Bipf.list_append(data, Bipf.mkBytes(isp_prev_data_feed!!))



        Bipf.list_append(data, Bipf.mkInt(data_goset.epoch))

        val subList = Bipf.mkList()
        for (sub in this.subscriptions) {
            val subListEntry = Bipf.mkList()
            Bipf.list_append(subListEntry, Bipf.mkString(sub.key))
            for (feed in sub.value) {
                Bipf.list_append(subListEntry, Bipf.mkBytes(feed))
            }
            Bipf.list_append(subList, subListEntry)
        }
        Bipf.list_append(data, subList)

        val pendingSubReqList = Bipf.mkList()
        for (req in pendingSubRequests) {
            val pendingSubReqListEntry = Bipf.mkList()
            Bipf.list_append(pendingSubReqListEntry, Bipf.mkString(req.key))
            Bipf.list_append(pendingSubReqListEntry, Bipf.mkBytes(req.value))
            Bipf.list_append(pendingSubReqList, pendingSubReqListEntry)
        }
        Bipf.list_append(data, pendingSubReqList)

        val recvReqList = Bipf.mkList()
        for (recv in receivedRequests) {
            val recvReqListEntry = Bipf.mkList()
            Bipf.list_append(recvReqListEntry, Bipf.mkString(recv.key))
            Bipf.list_append(recvReqListEntry, Bipf.mkBytes(recv.value.first))
            Bipf.list_append(recvReqListEntry, Bipf.mkBytes(recv.value.second))
            Bipf.list_append(recvReqList, recvReqListEntry)
        }
        Bipf.list_append(data, recvReqList)

        val bufferList = Bipf.mkList()
        for (buf in buffer) {
            val bufferListEntry = Bipf.mkList()
            Bipf.list_append(bufferListEntry, Bipf.mkString(buf.key))
            Bipf.list_append(bufferListEntry, Bipf.mkBytes(buf.value))
            Bipf.list_append(bufferList, bufferListEntry)
        }
        Bipf.list_append(data, bufferList)

        return Bipf.encode(data)!!
    }

}
