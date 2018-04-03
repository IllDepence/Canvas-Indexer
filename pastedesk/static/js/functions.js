function imgClick(node) {
    if (node.classList.contains('selected')) {
        node.classList.remove('selected');
    }
    else {
        node.classList.add('selected');
    }
    selected = document.querySelectorAll('img.selected');
    list = [];
    for (i=0; i<selected.length; i++) {
        list.push(selected[i].title);
    }
    sessionStorage.setItem('canvasList', JSON.stringify(list));
}

function postCuration() {
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
