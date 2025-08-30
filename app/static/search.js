         document.addEventListener('DOMContentLoaded', function() {
            var searchBar = document.getElementById("search_bar");
            searchBar.addEventListener("keypress", function(event) {
                if (event.key === "Enter") {
                    search();  // call your search function
                }
            });
         });

         function search(){
            const query = document.getElementById("search_bar").value;
            const words = query.split(" ");
            var urlString= words.join("_");
            window.location.href= "/search/".concat(urlString);
         }