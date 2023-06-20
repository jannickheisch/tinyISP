package nz.scuttlebutt.tremolavossbol

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.widget.Toast
import androidx.core.content.ContextCompat.checkSelfPermission
import androidx.core.content.FileProvider
import com.google.zxing.integration.android.IntentIntegrator
import org.json.JSONObject
import java.io.File
import java.util.*

import nz.scuttlebutt.tremolavossbol.tssb.LogTinyEntry
import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.Bipf.Companion.BIPF_LIST
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_APP_TEXTANDVOICE
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toBase64
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toHex


// pt 3 in https://betterprogramming.pub/5-android-webview-secrets-you-probably-didnt-know-b23f8a8b5a0c

class WebAppInterface(val act: MainActivity, val webView: WebView) {

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
                act.idStore.setNewIdentity(null) // creates new identity
                // eval("b2f_initialize(\"${tremolaState.idStore.identity.toRef()}\")")
                // FIXME: should kill all active connections, or better then the app
                act.finishAffinity()
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
            "publ:post" -> { // publ:post txt voice
                var t: String? = null
                if (args[1] != "null")
                    t = Base64.decode(args[1], Base64.NO_WRAP).decodeToString()
                var v: ByteArray? = null
                if (args.size > 2 && args[2] != "null")
                    v = Base64.decode(args[2], Base64.NO_WRAP)
                public_post_voice(t, v)
                return
            }
            /* no pivate post (yet) in tyinTremola
            "priv:post" -> { // atob(text) rcp1 rcp2 ...
                val rawStr = tremolaState.msgTypes.mkPost(
                                 Base64.decode(args[1], Base64.NO_WRAP).decodeToString(),
                                 args.slice(2..args.lastIndex))
                val evnt = tremolaState.msgTypes.jsonToLogEntry(rawStr,
                                            rawStr.encodeToByteArray())
                evnt?.let { rx_event(it) } // persist it, propagate horizontally and also up
                return
            }
            */
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

    fun public_post_voice(text: String?, voice: ByteArray?) {
        if (text != null)
            Log.d("wai", "post_voice t- ${text}/${text.length}")
        if (voice != null)
            Log.d("wai", "post_voice v- ${voice}/${voice.size}")
        val lst = Bipf.mkList()
        Bipf.list_append(lst, TINYSSB_APP_TEXTANDVOICE)
        Bipf.list_append(lst, if (text == null) Bipf.mkNone() else Bipf.mkString(text))
        Bipf.list_append(lst, if (voice == null) Bipf.mkNone() else Bipf.mkBytes(voice))
        val tst = Bipf.mkInt((System.currentTimeMillis() / 1000).toInt())
        Log.d("wai", "send time is ${tst.getInt()}")
        Bipf.list_append(lst, tst)
        val body = Bipf.encode(lst)
        if (body != null)
            act.tinyNode.publish_public_content(body)
    }

    fun return_voice(voice: ByteArray) {
        var cmd = "b2f_new_voice('" + voice.toBase64() + "');"
        Log.d("CMD", cmd)
        eval(cmd)
    }

    fun sendTinyEventToFrontend(entry: LogTinyEntry) {
        Log.d("wai","sendTinyEvent ${entry.body.toHex()}")
        sendToFrontend(entry.fid, entry.seq, entry.mid, entry.body)
    }

    fun sendToFrontend(fid: ByteArray, seq: Int, mid: ByteArray, payload: ByteArray) {
        Log.d("wai", "sendToFrontend seq=${seq} ${payload.toHex()}")
        val bodyList = Bipf.decode(payload)
        if (bodyList == null || bodyList.typ != BIPF_LIST) return
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
