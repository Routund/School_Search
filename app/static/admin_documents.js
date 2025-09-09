var dimmed = false;
var current_id = -1;
window.onload=function() {
    document.body.onkeyup = key_event;
    var source_list = document.getElementsByClassName('admin_source_button');
        
    for (let index = 0; index < source_list.length; index++) {
        source_list[index].addEventListener('click', display_source);
    }

    var new_popup = document.getElementsByClassName('admin_new_source_button');
    new_popup[0].addEventListener('click', new_source_popup);
    document.getElementById("confirm_new_source").addEventListener('click', send_new_source)
    document.getElementById('source_reparse').addEventListener('click', reparse)
}

function key_event(e) {
    if (e.keyCode == 27) new_source_hide();
}

function new_source_hide(){
    if (dimmed){
        dimmed = false;
        var overlay = document.getElementById('overlay');
        var info_box = document.getElementById('admin_new_source_form');
        overlay.classList.remove('dimmed');
        info_box.classList.remove('shown');
        document.getElementById("admin_source_succesful_insert").style.visibility="hidden";
    }
}

function new_source_popup(){
    dimmed = true;
    var overlay = document.getElementById('overlay');
    var info_box = document.getElementById('admin_new_source_form');
    overlay.classList.add('dimmed');
    info_box.classList.add('shown');
    document.getElementById("admin_source_succesful_insert").style.visibility="hidden";
}

function send_new_source(){
    url = document.getElementById('url').value;
    source_name = document.getElementById('name').value;
    try{
        new URL(url);
        console.debug("valid url");
    } catch (err) {
        console.debug("invalid url");
        return;
    }
    document.getElementById('loading_results').style.visibility = "visible"
    $.ajax({ 
        url: '/new_source', 
        type: 'POST', 
        contentType: 'application/json', 
        data: JSON.stringify({ 'url' : encodeURI(url), 'name' : source_name }),
        success: function(response) {
            document.getElementById("admin_source_succesful_insert").style.visibility="visible";
            document.getElementById('loading_results').style.visibility = "hidden"
        },
        error: function(msg){
            console.debug(msg.response);
            document.getElementById('loading_results').style.visibility = "hidden"
        }
    });
}

function display_source(){
    const url= this.getAttribute('url');
    const name = this.getAttribute('name');
    const id = this.getAttribute('id');
    current_id = parseInt(id);
    var title = document.getElementById("source_display_title");
    var url_display = document.getElementById("source_display_url");
    var reparse = document.getElementById("source_reparse");
    var reparse_success = document.getElementById("admin_source_succesful_reparse");
    title.textContent = name;
    url_display.textContent = "URL: ".concat(url);
    title.style.visibility = "visible";
    url_display.style.visibility = "visible";
    reparse.style.visibility = "visible";
    reparse_success.style.visibility = "hidden";
    url_display.setAttribute("href",url)
}

function reparse(){
    if (current_id != -1){
        $.ajax({ 
            url: '/reparse', 
            type: 'POST', 
            contentType: 'application/json', 
            data: JSON.stringify({ 'source_id': current_id }),
            success: function(response) {
                document.getElementById("admin_source_succesful_reparse").style.visibility="visible";
            },
            error: function(msg){
                console.debug(msg.response);
            }
        });
    }
}