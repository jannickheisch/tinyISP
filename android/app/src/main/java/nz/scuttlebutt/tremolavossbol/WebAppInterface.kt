package nz.scuttlebutt.tremolavossbol

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Base64
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.widget.Toast
import androidx.core.content.ContextCompat.checkSelfPermission
import com.google.zxing.integration.android.IntentIntegrator
import nz.scuttlebutt.tremolavossbol.crypto.SSBid
import nz.scuttlebutt.tremolavossbol.isp.ISP
import nz.scuttlebutt.tremolavossbol.isp.TinyISPProtocol
import org.json.JSONObject

import nz.scuttlebutt.tremolavossbol.tssb.LogTinyEntry
import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.Bipf.Companion.BIPF_LIST
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_APP_ISP
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_APP_TEXTANDVOICE
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_APP_KANBAN
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_APP_PRIVATETEXTVOICE
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toBase64
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toHex
import org.json.JSONArray


// pt 3 in https://betterprogramming.pub/5-android-webview-secrets-you-probably-didnt-know-b23f8a8b5a0c

class WebAppInterface(val act: MainActivity, val webView: WebView) {

    var frontend_ready = false

    @JavascriptInterface
    fun onFrontendRequest(s: String) {
        //handle the data captured from webview}
        Log.d("FrontendRequest", s)
        val args = s.split(" ")
        when (args[0]) {
            "onBackPressed" -> {
                (act as MainActivity)._onBackPressed()
            }
            "ready" -> {
                eval("b2f_initialize(\"${act.idStore.identity.toRef()}\")")
                frontend_ready = true
                act.tinyNode.beacon()
            }
            "reset" -> { // UI reset
                // erase DB content
                eval("b2f_initialize(\"${act.idStore.identity.toRef()}\")")
            }
            "restream" -> {
                for (fid in act.tinyRepo.listFeeds()) {
                    Log.d("wai", "restreaming ${fid.toHex()}")
                    var i = 1
                    while (true) {
                        val (payload,mid) = act.tinyRepo.feed_read_content(fid, i)
                        if (payload == null) break
                        Log.d("restream", "${i}, ${payload.size} Bytes")
                        sendToFrontend(fid, i, mid!!, payload)
                        i++
                    }
                }
            }
            "qrscan.init" -> {
                val intentIntegrator = IntentIntegrator(act)
                intentIntegrator.setBeepEnabled(false)
                intentIntegrator.setCameraId(0)
                intentIntegrator.setPrompt("SCAN")
                intentIntegrator.setBarcodeImageEnabled(false)
                intentIntegrator.initiateScan()
                return
            }
            "secret:" -> {
                if (importIdentity(args[1])) {
                    /*
                    tremolaState.logDAO.wipe()
                    tremolaState.contactDAO.wipe()
                    tremolaState.pubDAO.wipe()
                    */
                    act.finishAffinity()
                }
                return
            }
            "exportSecret" -> {
                val json = act.idStore.identity.toExportString()!!
                eval("b2f_showSecret('${json}');")
                val clipboard = act.getSystemService(ClipboardManager::class.java)
                val clip = ClipData.newPlainText("simple text", json)
                clipboard.setPrimaryClip(clip)
                Toast.makeText(act, "secret key was also\ncopied to clipboard",
                    Toast.LENGTH_LONG).show()
            }
            "wipe" -> {
                act.settings!!.resetToDefault()
                act.idStore.clearKeystore()
                act.idStore.setNewIdentity(null) // creates new identity
                act.tinyRepo.repo_reset()
                // eval("b2f_initialize(\"${tremolaState.idStore.identity.toRef()}\")")
                // FIXME: should kill all active connections, or better then the app
                act.finishAffinity()
            }
            "add:contact" -> {

                val id = args[1].substring(1,args[1].length-8)
                Log.d("ADD", id)
                act.tinyGoset._add_key(Base64.decode(id, Base64.NO_WRAP))
            }
            /* no alias publishing in tinyTremola
            "add:contact" -> { // ID and alias
                tremolaState.addContact(args[1],
                    Base64.decode(args[2], Base64.NO_WRAP).decodeToString())
                val rawStr = tremolaState.msgTypes.mkFollow(args[1])
                val evnt = tremolaState.msgTypes.jsonToLogEntry(rawStr,
                    rawStr.encodeToByteArray())
                evnt?.let {
                    rx_event(it) // persist it, propagate horizontally and also up
                    tremolaState.peers.newContact(args[1]) // inform online peers via EBT
                }
                    return
            }
            */
            "publ:post" -> { // publ:post tips txt voice
                val a = JSONArray(args[1])
                val tips = ArrayList<String>(0)
                for (i in 0..a.length()-1) {
                    val s = (a[i] as JSONObject).toString()
                    Log.d("publ:post", s)
                    tips.add(s)
                }
                var t: String? = null
                if (args[2] != "null")
                    t = Base64.decode(args[2], Base64.NO_WRAP).decodeToString()
                var v: ByteArray? = null
                if (args.size > 3 && args[3] != "null")
                    v = Base64.decode(args[3], Base64.NO_WRAP)
                public_post_with_voice(tips, t, v)
                return
            }
            "priv:post" -> { // priv:post tips atob(text) atob(voice) rcp1 rcp2 ...
                val a = JSONArray(args[1])
                val tips = ArrayList<String>(0)
                var t: String? = null
                if (args[2] != "null")
                    t = Base64.decode(args[2], Base64.NO_WRAP).decodeToString()
                var v: ByteArray? = null
                if (args.size > 3 && args[3] != "null")
                    v = Base64.decode(args[3], Base64.NO_WRAP)
                private_post_with_voice(tips, t, v, Base64.decode(args[4], Base64.NO_WRAP))
                return
            }
            "get:media" -> {
                if (checkSelfPermission(act, Manifest.permission.READ_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                    Toast.makeText(act, "No permission to access media files",
                        Toast.LENGTH_SHORT).show()
                    return
                }
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT); // , MediaStore.Images.Media.EXTERNAL_CONTENT_URI)
                intent.type = "image/*"
                act.startActivityForResult(intent, 1001)
            }

            "get:voice" -> { // get:voice
                val intent = Intent(act, RecordActivity::class.java)
                act.startActivityForResult(intent, 808)
                return
            }
            "play:voice" -> { // play:voice b64enc(codec2) from date)
                Log.d("wai", s)
                val voice = Base64.decode(args[1], Base64.NO_WRAP)
                val intent = Intent(act, PlayActivity::class.java)
                intent.putExtra("c2Data", voice)
                if (args.size > 2)
                    intent.putExtra("from", Base64.decode(args[2], Base64.NO_WRAP).decodeToString())
                if (args.size > 3)
                    intent.putExtra("date", Base64.decode(args[3], Base64.NO_WRAP).decodeToString())
                act.startActivity(intent)
                return
            }
            "kanban" -> { // kanban bid atob(prev) atob(operation) atob(arg1) atob(arg2) atob(...)
                /*var bid: String = args[1]
                var prevs: List<String>? = null
                if(args[2] != "null") // prevs == "null" for the first board event (create bord event)
                    prevs = Base64.decode(args[2], Base64.NO_WRAP).decodeToString().split(" ")
                var operation: String = Base64.decode(args[3], Base64.NO_WRAP).decodeToString()
                var argList: List<String>? = null
                if(args[4] != "null")
                    argList = Base64.decode(args[4], Base64.NO_WRAP).decodeToString().split(" ")

                 */
                //var data = JSONObject(Base64.decode(args[1], Base64.NO_WRAP).decodeToString())
                val bid: String? = if (args[1] != "null") args[1] else null
                val prev: List<String>? = if (args[2] != "null") Base64.decode(args[2], Base64.NO_WRAP).decodeToString().split(",").map{ Base64.decode(it, Base64.NO_WRAP).decodeToString()} else null
                val op: String = args[3]
                val argsList: List<String>? = if(args[4] != "null") Base64.decode(args[4], Base64.NO_WRAP).decodeToString().split(",").map{ Base64.decode(it, Base64.NO_WRAP).decodeToString()} else null

                if (bid != null) {
                    Log.d("KanbanPostBID", bid)
                    Log.d("KanbanPostPREV", prev.toString())
                }
                Log.d("KanbanPostOP", op)
                Log.d("KanbanPostARGS", args.toString())

                kanban(bid, prev , op, argsList)
            }
            "settings:set" -> {
                when(args[1]) {
                    "ble" -> {act.settings!!.setBleEnabled(args[2].toBooleanStrict())}
                    "udp_multicast" -> {act.settings!!.setUdpMulticastEnabled(args[2].toBooleanStrict())}
                    "websocket" -> {act.settings!!.setWebsocketEnabled(args[2].toBooleanStrict())}
                }
            }
            "isp:onboardRequest" -> {
                val isp_feed = Base64.decode(args[1], Base64.NO_WRAP)
                val client_ctrl_feed = act.idStore.new()

                act.tinyNode.publish_public_content(TinyISPProtocol.request_onboarding(isp_feed,client_ctrl_feed.verifyKey))
            }
            "isp:debug" -> {
                val isp = act.ispList[0]
                val lst = Bipf.mkList()
                Bipf.list_append(lst, Bipf.mkString("Hello"))
                Bipf.list_append(lst, Bipf.mkString("World"))
                isp.sendOverData(Bipf.encode(lst)!!)

            }
            "isp:subscribe" -> {
                val isp = act.ispList.find { it.ispID.contentEquals(Base64.decode(args[1], Base64.NO_WRAP)) }
                if (isp == null) {
                    throw Exception("unknown isp?")
                }
                isp.subscribe(Base64.decode(args[2], Base64.NO_WRAP))
            }
            "isp:response" -> {
                val isp = act.ispList.find { it.ispID.contentEquals(Base64.decode(args[1], Base64.NO_WRAP)) }
                if (isp == null) {
                    Log.e("unknow_isp", "unknonw: ${Base64.decode(args[1], Base64.NO_WRAP)}")
                    throw Exception("unknown isp?")
                }
                isp.respond_to_request(Base64.decode(args[2], Base64.NO_WRAP), args[3].toBooleanStrict())
            }
            "isp:farewell" -> {
                val isp = act.ispList.find { it.ispID.contentEquals(Base64.decode(args[1], Base64.NO_WRAP)) }
                isp!!.startFarewell()
            }
            else -> {
                Log.d("onFrontendRequest", "unknown")
            }
        }
    }

    fun eval(js: String) { // send JS string to webkit frontend for execution
        webView.post(Runnable {
            webView.evaluateJavascript(js, null)
        })
    }

    private fun importIdentity(secret: String): Boolean {
        Log.d("D/importIdentity", secret)
        if (act.idStore.setNewIdentity(Base64.decode(secret, Base64.DEFAULT))) {
            // FIXME: remove all decrypted content in the database, try to decode new one
            Toast.makeText(act, "Imported of ID worked. You must restart the app.",
                Toast.LENGTH_SHORT).show()
            return true
        }
        Toast.makeText(act, "Import of new ID failed.", Toast.LENGTH_LONG).show()
        return false
    }

    fun public_post_with_voice(tips: ArrayList<String>, text: String?, voice: ByteArray?) {
        if (text != null)
            Log.d("wai", "post_voice t- ${text}/${text.length}")
        if (voice != null)
            Log.d("wai", "post_voice v- ${voice}/${voice.size}")
        val lst = Bipf.mkList()
        Bipf.list_append(lst, TINYSSB_APP_TEXTANDVOICE)
        // add tips
        Bipf.list_append(lst, if (text == null) Bipf.mkNone() else Bipf.mkString(text))
        Bipf.list_append(lst, if (voice == null) Bipf.mkNone() else Bipf.mkBytes(voice))
        val tst = Bipf.mkInt((System.currentTimeMillis() / 1000).toInt())
        Log.d("wai", "send time is ${tst.getInt()}")
        Bipf.list_append(lst, tst)
        val body = Bipf.encode(lst)
        if (body != null)
            act.tinyNode.publish_public_content(body)
    }

    fun private_post_with_voice(tips: ArrayList<String>, text: String?, voice: ByteArray?, rcp: ByteArray) {
        if (text != null)
            Log.d("wai", "post_voice t- ${text}/${text.length}")
        if (voice != null)
            Log.d("wai", "post_voice v- ${voice}/${voice.size}")
        val lst = Bipf.mkList()
        Bipf.list_append(lst, TINYSSB_APP_PRIVATETEXTVOICE)
        // add tips
        Bipf.list_append(lst, if (text == null) Bipf.mkNone() else Bipf.mkString(text))
        Bipf.list_append(lst, if (voice == null) Bipf.mkNone() else Bipf.mkBytes(voice))
        val tst = Bipf.mkInt((System.currentTimeMillis() / 1000).toInt())
        Log.d("wai", "send time is ${tst.getInt()}")
        Bipf.list_append(lst, tst)
        Bipf.list_append(lst, Bipf.mkString(rcp.toBase64()))
        val body = Bipf.encode(lst)
        if (body == null)
            return
        Log.d("priv_post", "rcp: ${rcp.toHex()}")
        val isp = act.ispList.find { it.isSubscribedTo(rcp) }
        if (isp == null) {
            Log.d("Privat chat", "send via root")
            act.tinyNode.publish_public_content(body)
            return
        }


        val res = isp.c2cSendTo(rcp, body)
        Log.d("Privat chat", "send via c2c $res")
    }

    fun kanban(bid: String?, prev: List<String>?, operation: String, args: List<String>?) {
        val lst = Bipf.mkList()
        Bipf.list_append(lst, TINYSSB_APP_KANBAN)
        if (bid != null)
            Bipf.list_append(lst, Bipf.mkString(bid))
        else
            Bipf.list_append(lst, Bipf.mkString("null")) // Bipf.mkNone()

        if(prev != null) {
            val prevList = Bipf.mkList()
            for(p in prev) {
                Bipf.list_append(prevList, Bipf.mkString(p))
            }
            Bipf.list_append(lst, prevList)
        } else {
            Bipf.list_append(lst, Bipf.mkString("null")) // Bipf.mkNone()
        }

        Bipf.list_append(lst, Bipf.mkString(operation))

        if(args != null) {
            for(arg in args) {
                Bipf.list_append(lst, Bipf.mkString(arg))
            }
        }

        val body = Bipf.encode(lst)

        if (body != null) {
            Log.d("kanban", "published bytes: " + Bipf.decode(body))
            act.tinyNode.publish_public_content(body)
        }
        //val body = Bipf.encode(lst)
        //Log.d("KANBAN BIPF ENCODE", Bipf.bipf_list2JSON(Bipf.decode(body!!)!!).toString())
        //if (body != null)
            //act.tinyNode.publish_public_content(body)

    }

    fun return_voice(voice: ByteArray) {
        var cmd = "b2f_new_voice('" + voice.toBase64() + "');"
        Log.d("CMD", cmd)
        eval(cmd)
    }

    fun sendTinyEventToFrontend(entry: LogTinyEntry) {
        Log.d("wai","sendTinyEvent ${entry.body.toHex()}")
        val buf = Bipf.decode(entry.body)
        if (buf != null && buf.typ == BIPF_LIST) {
            val lst = Bipf.bipf_list2JSON(buf)
            if (lst!!.length() > 2) {
                if (lst[0] == "ISP" && lst[1] == TinyISPProtocol.TYPE_ONBOARDING_REQUEST && entry.fid.contentEquals(act.idStore.identity.verifyKey)) {
                    val ispID = Base64.decode(lst[2] as String, Base64.NO_WRAP)
                    val ctrl_feed = Base64.decode(lst[3] as String, Base64.NO_WRAP)
                    val isp = ISP(act, ispID, ctrl_feed, entry.mid)
                    act.ispList.add(isp)
                } else if (lst[0] == "ISP" && lst[1] == TinyISPProtocol.TYPE_ONBOARDING_RESPONSE) {
                    Log.d("wai", "recieved isp response")
                    Log.d("onboard_response", "ispID: ${act.ispList[0].ispID.toHex()}, contractId: ${act.ispList[0].contractID}")
                    val isp = act.ispList.find { it.ispID.contentEquals(entry.fid) && it.contractID.contentEquals(
                        Base64.decode(lst[2] as String, Base64.NO_WRAP)
                    ) }
                    if (isp != null) {
                        if (!(lst[3] as Boolean)) {
                            isp.delete()
                            act.ispList.remove(isp)
                        } else {
                            val isp_ctrl_feed = Base64.decode(lst[4] as String, Base64.NO_WRAP)
                            Log.d("wai", "isp accepted request (${isp_ctrl_feed.toHex()}")
                            isp.add_isp_ctrl_feed(isp_ctrl_feed)
                        }
                    }
                }
            }
        }
        sendToFrontend(entry.fid, entry.seq, entry.mid, entry.body)
    }

    fun sendToFrontend(fid: ByteArray, seq: Int, mid: ByteArray, payload: ByteArray) {
        Log.d("wai", "sendToFrontend seq=${seq} ${payload.toHex()}")
        val bodyList = Bipf.decode(payload)
        if (bodyList == null || bodyList.typ != BIPF_LIST) {
            Log.d("sendToFrontend", "decoded payload == null")
            return
        }
        val param = Bipf.bipf_list2JSON(bodyList)
        var hdr = JSONObject()
        hdr.put("fid", "@" + fid.toBase64() + ".ed25519")
        hdr.put("ref", mid.toBase64())
        hdr.put("seq", seq)
        var cmd = "b2f_new_event({header:${hdr.toString()},"
        cmd += "public:${param.toString()}"
        cmd += "});"
        Log.d("CMD", cmd)
        eval(cmd)
    }


}
