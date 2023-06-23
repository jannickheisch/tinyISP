package nz.scuttlebutt.tremolavossbol.tssb

import android.content.Context
import android.util.Log
import nz.scuttlebutt.tremolavossbol.MainActivity
import nz.scuttlebutt.tremolavossbol.utils.Bipf
import nz.scuttlebutt.tremolavossbol.utils.Bipf.Companion.BIPF_INT
import nz.scuttlebutt.tremolavossbol.utils.Bipf.Companion.BIPF_LIST
import nz.scuttlebutt.tremolavossbol.utils.Bipf.Companion.bipf_loads
import nz.scuttlebutt.tremolavossbol.utils.Bipf.Companion.varint_decode
import nz.scuttlebutt.tremolavossbol.utils.Constants
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.DMX_LEN
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.HASH_LEN
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.PKTTYPE_chain20
import nz.scuttlebutt.tremolavossbol.utils.Constants.Companion.TINYSSB_PKT_LEN
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.decodeHex
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toByteArray
import nz.scuttlebutt.tremolavossbol.utils.HelperFunctions.Companion.toHex
import java.io.File
import java.io.RandomAccessFile
import java.util.concurrent.locks.ReentrantLock

class Node(val context: MainActivity) {
    val NODE_ROUND_LEN = 5000L
    var log_offs = 0
    var chunk_offs = 0

    private val wantAccessLock = Any()


    fun loop(lck: ReentrantLock) {
        while (true) {
            lck.lock()
            beacon()
            lck.unlock()
            Thread.sleep(NODE_ROUND_LEN)
        }
    }

    fun beacon() { // called in regular intervals
        /*
        Serial.print("|dmxt|=" + String(dmxt_cnt) + ", |chkt|=" + String(blbt_cnt));
        int fcnt, ecnt, bcnt;
        stats(&fcnt, &ecnt, &bcnt);
        */
        Log.d("node", "beacon") // , stats: |feeds|=" + String(fcnt) + ", |entries|=" + String(ecnt) + ", |blobs|=" + String(bcnt));

        for (goset in context.gosetManager.sets) {
            if(goset.keys.size == 0)
                continue

            var v = ""
            val vect = Bipf.mkList()
            var vector = mutableMapOf<Int, Int>() // want vector for frontend
            var encoding_len = 0
            Log.d("Node", "offset: ${context.gosetManager.offs[goset]}")
            context.gosetManager.offs[goset] = (context.gosetManager.offs[goset]!! + 1) % goset.keys.size
            Bipf.list_append(vect, Bipf.mkInt(context.gosetManager.offs[goset]!!))
            var i = 0
            while (i < goset.keys.size) {
                val ndx = (context.gosetManager.offs[goset]!! + i) % goset.keys.size
                val key = goset.keys[ndx]
                val feed = context.tinyRepo.feeds[context.tinyRepo._feed_index(key)]
                val bptr = Bipf.mkInt(feed.next_seq)
                Bipf.list_append(vect, bptr)

                if (key.toHex() == "d55d38b7bc84fe4fe736445385121f1d8363f2c98f2780412cb60b9deb5d784a") {
                    Log.d("bptr", "${feed.next_seq}")
                    Log.d("prev:", "${feed.prev_hash.toHex()}")
                }
                val dmx = context.tinyDemux.compute_dmx(
                    key + feed.next_seq.toByteArray()
                            + feed.prev_hash
                )
                // Log.d("node", "dmx is ${dmx.toHex()}")
                val fct = { buf: ByteArray, fid: ByteArray?, _: String? ->
                    context.tinyNode.incoming_pkt(
                        buf,
                        fid!!
                    )
                }
                Log.d("arm", "for $ndx.${key.toHex()}.${feed.next_seq}")
                context.tinyDemux.arm_dmx(dmx, fct, key)
                v += (if (v.length == 0) "[ " else ", ") + "$ndx.${feed.next_seq}"
                vector[ndx] = feed.next_seq
                i++
                encoding_len += Bipf.encode(bptr)!!.size
                if (encoding_len > 100)
                    break
            }
            context.gosetManager.offs[goset] = (context.gosetManager.offs[goset]!! + i) % goset.keys.size
            if (vect.cnt > 1) {  // vect always has at least offs plus one element ?!
                val buf = Bipf.encode(vect)
                if (buf != null) {
                    context.tinyIO.enqueue(buf, context.tinyDemux.want_dmx[goset]!!)
                    Log.d("node", ">> sent WANT request ${v} ]")
                    update_progress(vector.toSortedMap().values.toList(), "me")
                }
            }

            // hunt for unfinished sidechains
            // FIXME: limit vector to 100B, rotate through set
            v = ""
            val chunkReqList = Bipf.mkList()
            val fdir = File(
                context.getDir(Constants.TINYSSB_DIR, Context.MODE_PRIVATE),
                context.tinyRepo.FEED_DIR
            )
            val r = context.tinyRepo
            for (k in goset.keys) {
                val f = File(fdir, k.toHex())
                if (!f.isDirectory || f.name.length != 2 * Constants.FID_LEN) continue
                val fid = f.name.decodeHex()
                val frec = context.tinyRepo.fid2rec(fid, true, if (goset.is_root_goset) context.tinyRepo.FEED_TYPE_ROOT else context.tinyRepo.FEED_TYPE_ISP_VIRTUAL)
                frec!!.next_seq = r.feed_len(fid) + 1
                for (fn in f.listFiles()) {
                    if (fn.name[0] != '!')
                        continue
                    var seq = fn.name.substring(1..fn.name.lastIndex).toInt()
                    val sz = fn.length().toInt()
                    var h = ByteArray(HASH_LEN)
                    Log.d("node", "need chunk ${fid.toHex().substring(0..19)}.${seq}")
                    if (sz == 0) { // must fetch first ptr from log
                        val pkt = r.feed_read_pkt(fid, seq)
                        if (pkt != null) {
                            h = pkt.sliceArray(DMX_LEN + 1 + 28..DMX_LEN + 1 + 28 + HASH_LEN - 1)
                            Log.d("node", "  having hash ${h.toHex()}")
                        } else {
                            Log.d("node", "  failed to find hash")
                            seq = -1
                        }

                    } else { // must fetch latest ptr from chain file
                        Log.d("node", "fetching chunk hash from file ${fn}")
                        val g = RandomAccessFile(fn, "rw")
                        g.seek(g.length() - HASH_LEN)
                        if (g.read(h) != h.size) {
                            Log.d("node", "could not read() after seek")
                            seq = -1;
                        } else {
                            var i = 0
                            while (i < HASH_LEN)
                                if (h[i].toInt() != 0)
                                    break;
                                else
                                    i++
                            if (i == HASH_LEN) // reached end of chain
                                seq = -1;
                        }
                    }
                    if (seq > 0) {
                        val nextChunk = sz / TINYSSB_PKT_LEN;
                        // FIXME: check if sidechain is already full, then swap '.' for '!' (e.g. after a crash)
                        val lst = Bipf.mkList()
                        val fidNr = goset.keys.indexOfFirst({ k ->
                            HelperFunctions.byteArrayCmp(k, fid) == 0
                        })
                        Bipf.list_append(lst, Bipf.mkInt(fidNr))
                        Bipf.list_append(lst, Bipf.mkInt(seq))
                        Bipf.list_append(lst, Bipf.mkInt(nextChunk))
                        Bipf.list_append(chunkReqList, lst)
                        val fct =
                            { pkt: ByteArray, x: Int -> context.tinyNode.incoming_chunk(pkt, x) }
                        v += (if (v.length == 0) "[ " else ", ") + "$fidNr.$seq.$nextChunk"
                        // Log.d("node", "need chunk $fidNr.$seq.$nextChunk, armed for ${h.toHex()}, list now ${chunkReqList.cnt} (${lst.cnt})")
                        context.tinyDemux.arm_blb(h, fct, fid, seq, nextChunk)
                    }
                }
            }
            if (chunkReqList.cnt > 0) {
                val buf = Bipf.encode(chunkReqList)
                if (buf != null) {
                    context.tinyIO.enqueue(buf, context.tinyDemux.chnk_dmx[goset]!!)
                    Log.d("node", ">> sent CHUNK request ${v} ]")
                }
            }
        }
    }

    fun incoming_pkt(buf: ByteArray, fid: ByteArray) {
        Log.d("node", "incoming logEntry ${buf.size}B")
        if (buf.size != TINYSSB_PKT_LEN) return
        context.tinyRepo.feed_append(fid, buf)
    }

    fun incoming_chunk(buf: ByteArray, blbt_ndx: Int) {
        Log.d("node", "incoming chunk ${buf.size}B, index=${blbt_ndx}")
        if (buf.size != TINYSSB_PKT_LEN) return
        context.tinyRepo.sidechain_append(buf, blbt_ndx)
    }

    fun publish_public_content(content: ByteArray): Boolean {
        val repo = context.tinyRepo
        Log.d("node", "publish_public_content ${content.size}B")
        val pkt = repo.mk_contentLogEntry(content, null)
        Log.d("node", "publish_public_content --> pkt ${if (pkt == null) 0 else pkt.size}B")
        Log.d("node", "publish_public_content --> content ${if (pkt == null) 0 else pkt.toHex()}B")
        if (pkt == null) return false
        return repo.feed_append(context.idStore.identity.verifyKey, pkt)
    }

    // all want vectors are sorted by the keys
    var wants = mutableMapOf<String, Pair<List<Int>, Long>>()  // from (device address): ( [want vector], timestamp)
    var max_want: List<Int>? = null
    var min_want: List<Int>? = null
    var old_want: List<Int>? = null
    var old_min: List<Int>? = null
    var old_min_from: String? = null

    // calculates current replication progress and sends update to frontend
    fun update_progress(want_vector: List<Int>, from: String) {

        if (!context.wai.frontend_ready)
            return

        var wantsChanged = false // if want vectors did change

        synchronized(wantAccessLock) {
            val iterator = wants.iterator()
            while (iterator.hasNext()) {
                val (k, v) = iterator.next()
                val (_, ts) = v
                if (System.currentTimeMillis() - ts > 30000 && k != from && k != "me") {
                    iterator.remove() // Safely remove the element using the iterator
                    print("remove old want")
                    wantsChanged = true
                }
            }
            if(wants[from]?.first != want_vector)
                wantsChanged = true
            wants[from] = Pair(want_vector, System.currentTimeMillis())

            if(!wantsChanged)
                return


            val all_vectors = wants.values.map { it.first }
            val new_max_want = all_vectors.reduce{acc, curr -> if (acc.size >= curr.size) acc else curr }.toMutableList() //return want vector with most entries
            val new_min_want = new_max_want.toMutableList()

            for (vec in all_vectors) {
                for (i in vec.indices) {
                    if(vec[i] > new_max_want[i]) {
                        new_max_want[i] = vec[i]
                    }

                    if(vec[i] < new_min_want[i]) {
                        new_min_want[i] = vec[i]
                    }
                }
            }

            var updated = false
            if (max_want != new_max_want) {
                old_want = wants["me"]?.first
                max_want = new_max_want
                updated = true
            }

            if (min_want != new_min_want) {
                if ((((new_min_want.sum()) < (old_min?.sum() ?: 0)) || (min_want == null) || !wants.containsKey(old_min_from)) && from != "me") {
                    old_min = new_min_want
                    old_min_from = from
                }
                min_want = new_min_want
                updated = true
            }

            if (updated || from == "me") {
                val min_want_entries = min_want?.sum() ?: 0
                val old_want_entries = old_want?.sum() ?: 0
                val old_min_entries = old_min?.sum() ?:0
                val curr_want_entries = wants["me"]?.first?.sum() ?: 0
                val max_want_entries = max_want?.sum() ?: 0

                Log.d("node","notify frontend: $min_want_entries, $old_min_entries, $old_want_entries, $curr_want_entries, $max_want_entries")

                context.wai.eval("b2f_update_progress($min_want_entries, $old_min_entries, $old_want_entries, $curr_want_entries, $max_want_entries)")
            }
        }

    }
}