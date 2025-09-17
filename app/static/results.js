document.addEventListener('DOMContentLoaded', function() {
var searchBar = document.getElementById("search_bar");
searchBar.addEventListener("keypress", function(event) {
    console.debug("AIAIAI")
    if (event.key === "Enter") {
        search();
    }
    change_filter_list
});
var filter = document.getElementById('filter_search_bar_icon');
filter.addEventListener('click', toggle_filter_dialogue);
var filter_apply = document.getElementById('filter_apply');
filter_apply.addEventListener('click');
});

function search(){
    const query = document.getElementById("search_bar").value;
    if (query == ""){
        return;
    }
    const words = query.split(" ");
    var urlString= words.join("_");
    window.location.href= "/search/".concat(urlString);
}

var dimmed = true

function toggle_filter_dialogue(){
    if (!dimmed){
        dimmed = true;
        var overlay = document.getElementById('overlay');
        var dialogue_box = document.getElementById('filter_dialogue');
        overlay.classList.add('dimmed');
        dialogue_box.classList.add('shown');
    }
    else{
        dimmed = false;
        var overlay = document.getElementById('overlay');
        var dialogue_box = document.getElementById('filter_dialogue');
        overlay.classList.remove('dimmed');
        dialogue_box.classList.remove('shown');
    }
}



function change_filter_list(){
    var source_boxes = document.getElementsByClassName('source_checkbox');
    toggle_filter_dialogue();
}

$(window).scroll(function() {
   if($(window).scrollTop() + $(window).height() == $(document).height()) {
        document.getElementById("loading_results").style.visibility="visible";
        $.ajax({ 
        url: '/files_extend', 
        type: 'POST', 
        contentType: 'application/json', 
        data: JSON.stringify({ 'query': document.getElementById("result_container").dataset.query}),
        success: function(response) {
            document.getElementById("loading_results").style.visibility="hidden";
            var files = response.files
            for (let i = 0; i < files.length; i++) {
                const file = files[i];

                const anchor = document.createElement('a');
                anchor.setAttribute("href",file[1]);
                anchor.setAttribute('target', '_blank');
                anchor.setAttribute('class', 'result_container');

                const title = document.createElement('h2');
                title.setAttribute('class','result_title');
                title.innerText = file[2];
                
                const source_text = document.createElement('h5');
                source_text.setAttribute('class','result_source');
                source_text.innerText = file[3];

                const preview = document.createElement('p');
                preview.setAttribute('class','result_text');
                preview.innerText = file[4];

                const divider = document.createElement('hr');
                divider.setAttribute('class','resultDivider');

                anchor.appendChild(title);
                anchor.appendChild(source_text);
                anchor.appendChild(preview);

                document.getElementById('result_container').append(anchor);
                document.getElementById('result_container').appendChild(divider);
            }
        },
        error: function(msg){
            console.debug(msg.response);
            document.getElementById("loading_results").style.visibility="hidden";
        }
    });
    
   }
});

