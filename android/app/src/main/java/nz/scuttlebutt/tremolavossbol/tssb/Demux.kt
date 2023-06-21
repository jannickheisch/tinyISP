package nz.scuttlebutt.tremolavossbol.tssb

import android.util.Log
import nz.scuttlebutt.tremolavossbol.MainActivity
import nz.scuttlebutt.tremolavossbol.crypto.SodiumAPI.Companion.sha256
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.DMX_LEN
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.DMX_PFX
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.HASH_LEN
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_PKT_LEN
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toHex

typealias Dmx_callback = ((ByteArray,ByteArray?,String?) -> Unit)?
typealias Chk_callback = ((ByteArray, Int) -> Unit)?

class Dmx { // dmx entry
    var dmx = ByteArray(DMX_LEN)
    var fct: Dmx_callback = null // void (*fct)(unsigned char*, int, unsigned char* aux);
    var aux: ByteArray? = null
}

class Chk { // chunk entry
    var h: ByteArray? = null // HASH_LEN
    var fct: Chk_callback = null
    var fid: ByteArray? = null
    var seq: Int = 0
    var bnr: Int = 0
}

class Demux(val context: MainActivity) {
    val dmxt = ArrayList<Dmx>()
    val chkt = ArrayList<Chk>()

    val want_dmx = mutableMapOf<GOset, ByteArray>()
    val chnk_dmx = mutableMapOf<GOset, ByteArray>()

    fun dmxt_find(dmx: ByteArray): Dmx? {
        for (d in dmxt) {
            // Log.d("demux", "compare in=${dmx.toHex()} with stored=${d.dmx.toHex()}")
            if (dmx.contentEquals(d.dmx))
                return d
        }
        // Log.d("demux", "dmxt_find - nothing for ${dmx.toHex()}")
        return null
    }

    fun blbt_find(h: ByteArray): Chk? {
        for (b in chkt)
            if (h.contentEquals(b.h))
                return b
        return null
    }

    fun arm_dmx(dmx: ByteArray, fct: Dmx_callback =null, aux: ByteArray? =null) {
        Log.d("arm_dmx", "dmx: ${dmx.toHex()}, fct: ${fct.toString()}, aux: ${aux?.toHex()}")
        var d = dmxt_find(dmx)
        if (fct == null) { // del
            dmxt.remove(d)
            return
        }
        if (d == null) {
            d = Dmx()
            dmxt.add(d)
        }
        d.dmx = dmx
        d.fct = fct
        d.aux = aux;
    }

    fun arm_blb(h: ByteArray, fct: Chk_callback =null, fid: ByteArray? =null, seq: Int =-1, bnr: Int =-1): Int {
        var b = blbt_find(h)
        if (fct == null) { // del
            chkt.remove(b)
            return -1;
        }
        if (b == null) {
            b = Chk()
            chkt.add(b)
        }
        b.h = h
        b.fct = fct
        b.fid = fid
        b.seq = seq
        b.bnr = bnr
        return chkt.indexOf(b)
    }

    fun compute_dmx(buf: ByteArray) : ByteArray {
        return (DMX_PFX + buf).sha256().sliceArray(0..DMX_LEN-1)
    }

    fun on_rx(buf: ByteArray, sender: String? = null): Boolean { // crc already removed
        val h = buf.sha256().sliceArray(0..HASH_LEN - 1)
        Log.d("demux", "on_rx ${buf.size} bytes: 0x${buf.toHex()}, h=${h.toHex()}")
        var rc = false
        val d = dmxt_find(buf.sliceArray(0..DMX_LEN-1))
        if (d != null && d.fct != null) {
            Log.d("demux", "calling dmx=${d.dmx.toHex()} fct=[${d.fct}] aux=${d.aux} sender=$sender")
            d.fct!!.invoke(buf, d.aux, sender)
                rc = true
        }
        if (buf.size == TINYSSB_PKT_LEN) {
            Log.d("demux", "buf.size == TINYSSB_PKT_LEN")
            val b = blbt_find(h)
            if (b != null) {
                b.fct!!.invoke(buf, chkt.indexOf(b))
                rc = true
            }
        }
        return rc
    }

    fun set_want_dmx(goset: GOset) {
        //Log.d("demux", "SET NEW DMX FOR STATE ${goset_state.toHex()}")

        //undefine current handler

        if(context.tinyDemux.want_dmx[goset] != null)
            arm_dmx(context.tinyDemux.want_dmx[goset]!!, null, null)

        if(context.tinyDemux.chnk_dmx[goset] != null)
            arm_blb(context.tinyDemux.chnk_dmx[goset]!!, null, null, 0, 0)

        val want_dmx = compute_dmx("want".encodeToByteArray() + goset.state)
        val chnk_dmx = compute_dmx("blob".encodeToByteArray() + goset.state)
        arm_dmx(want_dmx, { buf:ByteArray, aux:ByteArray?, sender:String? -> goset.incoming_want_request(buf,null, sender)}, null)
        arm_dmx(chnk_dmx, { buf:ByteArray, aux:ByteArray?, _ -> goset.incoming_chunk_request(buf,aux)})
        context.tinyDemux.want_dmx[goset] = want_dmx
        context.tinyDemux.chnk_dmx[goset] = chnk_dmx
        //Log.d("demux", "GOset state is  ${goset_state.toHex()}")
        Log.d("demux", "new WANT dmx is ${want_dmx.toHex()}")
        Log.d("demux", "new BLOB dmx is ${chnk_dmx.toHex()}")
    }
}

// eof