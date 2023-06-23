
"use strict";

var ISP_TYPE_ANNOUNCEMENT = "announcement"

function menu_isp_announcements() {
    closeOverlay()
    overlayIsActive = true

    document.getElementById("isp-announcements-overlay").style.display = 'initial';
    document.getElementById("overlay-bg").style.display = 'initial';

    document.getElementById("isp-announcements-list").innerHTML = ''

    for (var isp of tremola.isp.announcements)
        menu_isp_announcements_create_entry(isp)
}

function send_onboardRequest(isp_id) {
    var id = isp_id.slice(1,-8) // remove @ and .ed25519
    backend("isp:onboardRequest " + id)

}

// isp-announcements_list
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
