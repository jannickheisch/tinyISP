
"use strict";

var ISP_TYPE_ANNOUNCEMENT = "announcement"
var ISP_TYPE_ONBOARD_REQUEST = "onboard_request"
var ISP_TYPE_ONBOARD_RESPONSE = "onboard_response"

var isp_context_menu;
var curr_isp;

function b2f_received_subRequest(ispID, id, ref) {
    console.log("recieved subRequest:", ispID, id, ref)
    var isp = tremola.isp.established["@" + ispID + ".ed25519"]
    isp.requests["@" + id + ".ed25519"] = ref
    persist()
}

function b2f_received_subResponse(isp, id, accepted) {
    var fid = "@" + id + ".ed25519"
    var isp_id = "@" + isp + ".ed25519"
    console.log("recieved sub response from", isp_id)
    if (accepted) {
        tremola.isp.established[isp_id].pendingSub.pop(fid)
        tremola.isp.established[isp_id].subscriptions.push(fid)
        isp_sub_request_create_entry(fid)
    }
    persist()
}

function send_onboardRequest(isp_id) {
    var id = isp_id.slice(1,-8) // remove @ and .ed25519
    backend("isp:onboardRequest " + id)

}

function menu_new_isp_request() {
    closeOverlay()
    qr_scan_isp = true
    document.getElementById('new-isp-overlay').style.display = 'initial';
    document.getElementById('overlay-bg').style.display = 'initial';

    overlayIsActive = true;
}

function load_isp_list() {
    console.log("load_is_list()")
    document.getElementById("lst:isp").innerHTML = '';

    for (var isp in tremola.isp.established) {
        update_isp_item(isp)
    }

    for (var isp in tremola.isp.requested) {
        update_isp_item(isp)
    }

}

function update_isp_item(isp) { // [ id, { "alias": "thealias", "initial": "T", "color": "#123456" } ] }
    var isAwaitingResponse = isp in tremola.isp.requested
    var status = isAwaitingResponse ? "Onboarding requested..." : "established"
    var row, item = document.createElement('div'), bg;
    item.setAttribute('style', 'padding: 0px 5px 10px 5px;'); // old JS (SDK 23)

    var cl, item, bg, row, cnt;
    cl = document.getElementById('lst:isp');
    item = document.createElement('div');
    item.setAttribute('style', "padding: 0px 5px 10px 5px; margin: 3px 3px 6px 3px;");
    if (isAwaitingResponse) bg = ' gray'; else bg = ' light';
    row = "<button class='board_item_button w100" + bg + "' onclick='isp_menu(\"" + isp + "\")' style='overflow: hidden; position: relative;'>";
    row += "<div style='white-space: nowrap;'><div style='text-overflow: ellipsis; overflow: hidden;'>" + isp + "</div>";
    row += "<div style='text-overflow: clip; overflow: ellipsis;'><font size=-2>" + status + "</font></div></div>";
    row += "</button>";
    row += ""
    item.innerHTML = row;
    cl.appendChild(item);
}

function isp_debug() {
    backend("isp:debug")
}

function close_isp_context_menu() {
    if (isp_context_menu) {
        console.log("close overlay")
        var context_menu = document.getElementById(isp_context_menu)
        if (context_menu) {
            context_menu.style.display = 'none';
            isp_context_menu = null
            return true
        }

    }
    isp_context_menu = null
    return false
}

function isp_menu(isp_id) {
    closeOverlay()
    curr_isp = isp_id
    document.getElementById('overlay-bg').style.display = 'initial'
    document.getElementById("div:isp_menu").style.display = 'initial'
    overlayIsActive = true;
}

function contextmenu_isp_sub_request() {
    close_isp_context_menu()
    overlayIsActive = true
    isp_context_menu = "isp-sub-overlay"

    document.getElementById("isp-sub-overlay").innerHTML = ""

    for (var c in tremola.contacts) {
        isp_sub_request_create_entry(c)
    }

    document.getElementById("isp-sub-overlay").style.display = "initial";

}

// adds an entry to the invite menu or updates an already existing entry
function isp_sub_request_create_entry(id) {
    var isp = tremola.isp.established[curr_isp]

    if (id in tremola.isp.established || id in tremola.isp.requested) // you cant subscribe to an isp
        return


    if (document.getElementById("div:isp_menu").style.display == 'none')
        return

    if (document.getElementById('isp-invite_' + id)) {
        if (isp.subscriptions.indexOf(id) >= 0)
            document.getElementById('isp-invite_' + id).outerHTML = ''
        else if (isp.pendingSub.indexOf(id) >= 0) {
            document.getElementById('isp-invite_' + id).classList.add("gray")
            document.getElementById('isp-invite_author_' + id).innerHTML = 'Already requested'
            document.getElementById('isp-invite_btn_' + id).style.display = 'none'
        } else {
            console.log("enable invite for" + id)
            document.getElementById('isp-invite_' + id).classList.remove("gray")
            document.getElementById('isp-invite_author_' + id).innerHTML = ''
            document.getElementById('isp-invite_btn_' + id).style.display = 'initial'
        }


        return
    }

    if (id == myId || isp.subscriptions.indexOf(id) >= 0)
        return

    var isAlreadyRequested = isp.pendingSub.indexOf(id) >= 0
    var bg = isAlreadyRequested ? ' gray' : ' light'

    var invHTML = "<div id='isp-invite_" + id + "' class='kanban_invitation_container " + bg + "' style='width:95%; margin: 5px 0px 7px 5px;' >"
    invHTML += "<div class='kanban_invitation_text_container' >"
    invHTML += "<div style='grid-area: name; padding-top: 5px; padding-left: 10px;font-size:15px'>" + tremola.contacts[id].alias + "</div>"

    if (isAlreadyRequested)
        invHTML += "<div id='isp-invite_author_" + id + "' style='grid-area: author; padding-top: 2px; padding-left: 10px;font-size:8px'>Already Invited</div></div>"
    else
        invHTML += "<div id='isp-invite_author_" + id + "' style='grid-area: author; padding-top: 2px; padding-left: 10px;font-size:8px'></div></div>"

    invHTML += "<div style='grid-area: btns;justify-self:end;display: flex;justify-content: center;align-items: center;'>"
    invHTML += "<div style='padding-right:8px;'>"
    if (!isAlreadyRequested)
        invHTML += "<button id='isp-invite_btn_" + id + "' class='flat passive buttontext' style=\"height: 40px; color: red; background-image: url('img/send.svg');width: 35px;\" onclick='btn_request_sub(\"" + id + "\", \"" + curr_isp + "\")'>&nbsp;</button>"
    invHTML += "</div></div></div>"

    document.getElementById("isp-sub-overlay").innerHTML += invHTML
}

function btn_request_sub(id, isp) {
    backend("isp:subscribe " + isp.slice(1,-8) + " " + id.slice(1,-8))
    tremola.isp.established[isp].pendingSub.push(id)
    isp_sub_request_create_entry(id)
    persist()
}

function contextmenu_isp_requests_lst() {
    close_isp_context_menu()
    overlayIsActive = true
    isp_context_menu = "isp-requests-overlay"

    document.getElementById("isp-requests-overlay").innerHTML = ""

    console.log("#requets: ", Object.keys(tremola.isp.established[curr_isp].requests).length)

    for (var req in tremola.isp.established[curr_isp].requests)
        isp_requests_create_entry(req)

    document.getElementById("isp-requests-overlay").style.display = 'initial'


}

function isp_requests_create_entry(id) {

    var isp = tremola.isp.established[curr_isp]

    var reqID = id + "_" + curr_isp

    if (document.getElementById("isp_requests_" + reqID)) {
        if (!(id in isp.requests))
            document.getElementById("isp_requests_" + reqID).outerHTML = ""
        return
    }


    if (isp.subscriptions.indexOf(id) >= 0) // already subscribed
        return

    console.log("Create invitation for reqID: " + reqID)

    if(!(id in isp.requests))
        return

    var invHTML = "<div id='isp_requests_" + reqID + "' class='kanban_invitation_container'>"
    invHTML += "<div class='kanban_invitation_text_container'>"
    invHTML += "<div id='isp_requests_" + reqID + "_name' style='grid-area: name; padding-top: 5px; padding-left: 10px;font-size:15px'>" + id2b32(id) + "</div>"
    invHTML += "<div style='grid-area: author; padding-top: 2px; padding-left: 10px;font-size:8px'></div></div>"

    invHTML += "<div style='grid-area: btns;justify-self:end;display: flex;justify-content: center;align-items: center;'>"
    invHTML += "<div style='padding-right:8px;'>"
    //invHTML += "<div style='padding-right:10px;'>"
    invHTML += "<button class='flat passive buttontext' style=\"height: 40px; background-image: url('img/checked.svg'); width: 35px;margin-right:10px;background-color: var(--passive)\" onclick='btn_accept_sub(\"" + curr_isp + "\", \"" + id + "\")'>&nbsp;</button>"//</div>"
    invHTML += "<button class='flat passive buttontext' style=\"height: 40px; color: red; background-image: url('img/cancel.svg');width: 35px;background-color: var(--passive)\" onclick='btn_decline_sub(\"" + curr_isp + "\", \"" + id + "\")'>&nbsp;</button>"
    invHTML += "</div></div></div>"

    document.getElementById("isp-requests-overlay").innerHTML += invHTML
}

function btn_accept_sub(isp, id) {
    delete tremola.isp.established[isp].requests[id]
    tremola.isp.established[isp].subscriptions.push(id)
    var isp_id = isp.slice(1,-8)
    backend("isp:response " + isp_id + " " + id.slice(1,-8) + " " + "true")
    isp_requests_create_entry(id)
    var val = id2b32(id);
    tremola.contacts[id] = {
        "alias": val, "initial": val.substring(0, 1).toUpperCase(),
        "color": colors[Math.floor(colors.length * Math.random())]
    };
    var recps = [myId, id];
    var nm = recps2nm(recps);
    tremola.chats[nm] = {
        "alias": "Chat w/ " + val, "posts": {}, "members": recps,
        "touched": Date.now(), "lastRead": 0, "timeline": new Timeline()
    };
    load_chat_list()
    load_contact_list();
    persist()
}

function btn_decline_sub(isp, id) {
    delete tremola.isp.established[isp].requests[id]
    isp_requests_create_entry(id)
    var isp_id = isp.slice(1,-8)
    var fid = id.slice(1,-8)
    backend("isp:response " + isp_id + " " + fid + " " + "false")
    persist()
}

/*
<div id="isp-announcements-overlay" class="qr-overlay">
    <div>
      <b>Available ISPs</b>
    </div>

    <div id="isp-announcements-list" style="overflow-x: hidden;overflow-y: scroll;max-height: 70vh;"></div>
</div>

function menu_isp_announcements() {
 closeOverlay()
 overlayIsActive = true

 document.getElementById("isp-announcements-overlay").style.display = 'initial';
 document.getElementById("overlay-bg").style.display = 'initial';

 document.getElementById("isp-announcements-list").innerHTML = ''

 for (var isp of tremola.isp.announcements)
     menu_isp_announcements_create_entry(isp)
}

function menu_isp_announcements_create_entry(isp) {
    console.log("display ISP:", isp)
    var announcements = tremola.isp.announcements

    if (document.getElementById("isp-announcements-overlay").style.display == 'none')
        return

    if (document.getElementById('isp_announcement_' + isp)) {
        if (tremola.isp.subscribed.includes(isp))
            document.getElementById('isp_announcement_' + isp).outerHTML = ''
        else if (tremola.isp.pending.includes(isp)) {
            document.getElementById('isp_announcement_' + isp).classList.add("gray")
            document.getElementById('isp_announcement_name_' + isp).innerHTML = 'Response pending'
            document.getElementById('isp_announcement_btn_' + isp).style.display = 'none'
        } else {
            console.log("enable invite for" + isp)
            document.getElementById('isp_announcement_' + isp).classList.remove("gray")
            document.getElementById('isp_announcement_name_' + isp).innerHTML = ''
            document.getElementById('isp_announcement_btn_' + isp).style.display = 'initial'
        }
        return
    }

    if (tremola.isp.subscribed.includes(isp))
        return

    var isAlreadyRequested = tremola.isp.pending.includes(isp)
    var bg = isAlreadyRequested ? ' gray' : ' light'

    var invHTML = "<div id='isp_announcement_" + isp + "' class='kanban_invitation_container " + bg + "' style='width:95%; margin: 5px 0px 7px 5px;' >"
    invHTML += "<div class='kanban_invitation_text_container' >"
    invHTML += "<div style='grid-area: name; padding-top: 5px; padding-left: 10px;font-size:15px'>" + tremola.contacts[isp].alias + "</div>"

    if (isAlreadyRequested)
        invHTML += "<div id='isp_announcement_name_" + isp + "' style='grid-area: author; padding-top: 2px; padding-left: 10px;font-size:8px'>Already Invited</div></div>"
    else
        invHTML += "<div id='isp_announcement_name_" + isp + "' style='grid-area: author; padding-top: 2px; padding-left: 10px;font-size:8px'></div></div>"

    invHTML += "<div style='grid-area: btns;justify-self:end;display: flex;justify-content: center;align-items: center;'>"
    invHTML += "<div style='padding-right:8px;'>"
    if (!isAlreadyRequested)
        invHTML += "<button id='isp_announcement_btn_" + isp + "' class='flat passive buttontext' style=\"height: 40px; color: red; background-image: url('img/send.svg');width: 35px;\" onclick='send_onboardRequest(\"" + isp + "\")'>&nbsp;</button>"
    invHTML += "</div></div></div>"

    document.getElementById("isp-announcements-list").innerHTML += invHTML
}
*/