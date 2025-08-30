window.onclick = function(e) {
    if (!e.target.matches('#username_button')) {
        console.debug(e.target)
        var myDropdown = document.getElementById("top_bar_dropdown-content");
        if (myDropdown.style.visibility == "visible"){
            myDropdown.style.visibility = "hidden";
        }
    }
    else{
        var myDropdown = document.getElementById("top_bar_dropdown-content");
        myDropdown.style.visibility = "visible";
    }
}

function username_dropdown(){
    document.getElementById("top_bar_dropdown-content").style.visibility = "visible";
}