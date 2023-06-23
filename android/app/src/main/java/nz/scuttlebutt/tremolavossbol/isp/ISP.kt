package nz.scuttlebutt.tremolavossbol.isp

import android.content.Context
import android.util.Log
import nz.scuttlebutt.tremolavossbol.MainActivity
import nz.scuttlebutt.tremolavossbol.tssb.GOset
import nz.scuttlebutt.tremolavossbol.tssb.LogTinyEntry
import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.Bipf_e
import nz.scuttlebutt.tremolavossbol.utils.Constants
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toHex


const val STATE_ONBOARD_REQUESTED = "onboard_requested"
const val STATE_ONBOARD_ACK = "onboard_ack"
const val STATE_ESTABLISHED = "established"


class ISP {

    private var data_goset: GOset
    private var isp_data_feeds: ArrayList<ByteArray>
    private var client_data_feeds: ArrayList<ByteArray>
    private var context: MainActivity
    private var state: String
    private var ctrl_goset: GOset
    var contractID: ByteArray
    private var client_ctrl_feed: ByteArray
    private var isp_ctrl_feed: ByteArray?
    var ispID: ByteArray

    constructor(context: MainActivity, ispID: ByteArray, client_ctrl_feed: ByteArray, contractID: ByteArray) {
        this.context = context
        this.ispID = ispID
        this.client_ctrl_feed = client_ctrl_feed
        this.contractID = contractID

        val add_ctrl_key_callback = {key: ByteArray -> context.feedPub.subscribe(key, {entry: LogTinyEntry ->  on_ctrl_rx(entry) })}
        val ctrl_dmx = "ctrl" + context.idStore.identity.verifyKey.toHex() + contractID.toHex()
        this.ctrl_goset = context.gosetManager.add_goset(add_ctrl_key_callback, ctrl_dmx)
        this.ctrl_goset._add_key(client_ctrl_feed)
        this.ctrl_goset.adjust_state()

        val add_data_key_callback = {key: ByteArray -> context.feedPub.subscribe(key, {entry: LogTinyEntry ->  on_data_rx(entry) })}
        val data_dmx = "data" + context.idStore.identity.verifyKey.toHex() + contractID.toHex()
        this.data_goset =  context.gosetManager.add_goset(add_data_key_callback, data_dmx, 0)
        this.client_data_feeds = ArrayList<ByteArray>()
        this.isp_data_feeds = ArrayList<ByteArray>()

        this.isp_ctrl_feed = null

        this.state = STATE_ONBOARD_REQUESTED
    }

    fun on_ctrl_rx(entry: LogTinyEntry) {
        Log.d("ISP", "received log entry")
        val buf = Bipf.decode(entry.body)

        if (!entry.fid.contentEquals(isp_ctrl_feed))
            return

        if (buf == null)
            return
        val lst = bipf_to_arraylist(buf)
        if (lst == null || lst.size < 2)
            return

        if (lst[0] != "ISP")
            return

        when(lst[1]) {
            TinyISPProtocol.TYPE_ONBOARDING_ACK -> on_onboard_ack(lst[2] as ByteArray)
        }
    }

    fun on_data_rx(entry: LogTinyEntry) {

    }

    fun on_onboard_ack(data_feed: ByteArray) {
        isp_data_feeds.add(data_feed)
        data_goset._add_key(data_feed)
        data_goset.adjust_state()

        state = STATE_ESTABLISHED
    }

    fun add_isp_ctrl_feed(feed_id: ByteArray) {
        if (isp_ctrl_feed != null)
            return

        ctrl_goset._add_key(feed_id)
        ctrl_goset.adjust_state()
        isp_ctrl_feed = feed_id
        this.state = STATE_ONBOARD_ACK

        send_onboard_ack()
    }

    fun send_onboard_ack() {
        val fid = context.idStore.new().verifyKey
        client_data_feeds.add(fid)
        data_goset._add_key(fid)
        data_goset.adjust_state()
        sendOverCtrl(TinyISPProtocol.onboard_ack(fid))
    }

    fun sendOverCtrl(buf: ByteArray) {
        val pkt = context.tinyRepo.mk_contentLogEntry(buf, client_ctrl_feed)
        if (pkt == null) return
        context.tinyRepo.feed_append(client_ctrl_feed, pkt)
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

    fun delete() {
        context.tinyRepo.remove_feed(client_ctrl_feed)
    }



}



