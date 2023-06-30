package nz.scuttlebutt.tremolavossbol.isp

import android.util.Log
import androidx.core.graphics.createBitmap
import nz.scuttlebutt.tremolavossbol.tssb.LogTinyEntry
import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toHex

class FeedPub {
    val subscriptions = mutableMapOf<String, ArrayList<(LogTinyEntry) -> Unit>>()
    private val lock = Any()

    fun subscribe(fid: ByteArray, callback: (LogTinyEntry) -> Unit) {
        synchronized(lock) {
            if (subscriptions.containsKey(fid.toHex())) {
                subscriptions[fid.toHex()]!!.add(callback)
                return
            }

            Log.d("Feedpub", "subscribed to ${fid.toHex()}")
            val tmplist = ArrayList<(LogTinyEntry) -> Unit>()
            tmplist.add(callback)
            subscriptions[fid.toHex()] = tmplist
        }
    }

    fun unsubscribe(fid: ByteArray, callback: (LogTinyEntry) -> Unit) {
        if (!subscriptions.containsKey(fid.toHex()))
            return

        if (subscriptions[fid.toHex()]!!.contains(callback))
            subscriptions[fid.toHex()]!!.remove(callback)
    }

    fun unsubscribe(fid: ByteArray) {
        subscriptions.remove(fid.toHex())
    }

    fun on_rx(entry: LogTinyEntry) {
        Log.d("FeedPub", "recieved Tiny Log entry,  ${entry.fid.toHex()}")
        // Log.d("FeedPub", "${ISP.bipf_to_arraylist(Bipf.decode(entry.body))}")
        if (!subscriptions.containsKey(entry.fid.toHex())) {
            Log.d("FeedPub", "feed has no subscriptions:")
            return
        }


        for (callback in subscriptions[entry.fid.toHex()]!!) {
            callback(entry)
            Log.d("FeedPub", "called callback")
        }
    }

}