function setSelects() {
    // mark all Canvases saved in sessionStorage as selected
    // this is called at the end of every page load
    list_json = JSON.parse(sessionStorage.getItem('canvasList'));
    if (list_json != null) {
        for (i=0; i<list_json.length; i++) {
            to_select = document.querySelector('img[can="'+list_json[i]['can']+'"]');
            to_select.classList.add('selected');
        }
    }
}

function imgClick(node) {
    // toggle selection of a Canvas
    // (for each toggle the sessionStorage Canvas list is rebuilt)
    if (node.classList.contains('selected')) {
        node.classList.remove('selected');
    }
    else {
        node.classList.add('selected');
    }
    selected = document.querySelectorAll('img.selected');
    list = [];
    for (i=0; i<selected.length; i++) {
        list.push({'man':selected[i].getAttribute('man'),
                   'can':selected[i].getAttribute('can')});
    }
    sessionStorage.setItem('canvasList', JSON.stringify(list));
}

function postCuration() {
    // validate form fields and submit form
    list_json = sessionStorage.getItem('canvasList');
    title = document.querySelector('#cur_title').value;
    if (list_json && title.length > 0) {
        json_field = document.querySelector('#cur_json');
        json_field.value = list_json;
        form = document.querySelector('#cur_form');
        form.submit();
        return true;
    }
    return false;
}
