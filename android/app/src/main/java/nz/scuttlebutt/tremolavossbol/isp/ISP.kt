package nz.scuttlebutt.tremolavossbol.isp

import android.content.Context
import android.util.AtomicFile
import android.util.Log
import androidx.core.util.writeBytes
import nz.scuttlebutt.tremolavossbol.MainActivity
import nz.scuttlebutt.tremolavossbol.tssb.GOset
import nz.scuttlebutt.tremolavossbol.tssb.LogTinyEntry
import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.Bipf_e
import nz.scuttlebutt.tremolavossbol.utils.Constants
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.GOSET_DMX_STR
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toHex
import java.io.File


const val STATE_ONBOARD_REQUESTED = "onboard_requested"
const val STATE_ONBOARD_ACK = "onboard_ack"
const val STATE_ESTABLISHED = "established"


class ISP {


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

        this.state = STATE_ONBOARD_REQUESTED
        persist()
    }



    fun on_ctrl_rx(entry: LogTinyEntry) {
        Log.d("on ctrl feed", "received: ${bipf_to_arraylist(Bipf.decode(entry.body)!!)}, from ${entry.fid.toHex()}, expected: ${isp_ctrl_feed?.toHex()}")
        Log.d("ISP", "received log entry")
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
        }
    }

    fun on_data_rx(entry: LogTinyEntry) {
        Log.d("on data feed", "received: ${bipf_to_arraylist(Bipf.decode(entry.body)!!)}, from ${entry.fid.toHex()}, expected: ${isp_data_feed?.toHex()}")
        if(!entry.fid.contentEquals(isp_data_feed))
            return

        val buf = Bipf.decode(entry.body)

        if (buf == null)
            return
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
        Log.d("send_onboard_ack()", "send over ctrl")
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

    constructor(context: MainActivity, isp_id: ByteArray, contractID: ByteArray, client_ctrl_feed: ByteArray, state: String, isp_ctrl_feed: ByteArray?, client_data_feeds: ArrayList<ByteArray>?, isp_data_feed: ByteArray?, isp_prev_data_feed: ByteArray?, goset_epoch: Int) {
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

            return ISP(context, isp_id, contractID, client_ctrl_feed, state, isp_ctrl_feed, client_data_feed, isp_data_feed, isp_prev_data_feed, goset_epoch)
        }

        fun bipf_to_arraylist(buf: Bipf_e): ArrayList<Any?>? {
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

        return Bipf.encode(data)!!
    }



}



