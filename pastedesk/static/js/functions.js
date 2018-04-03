function imgClick(node) {
    if (node.classList.contains('selected')) {
        node.classList.remove('selected')
    }
    else {
        node.classList.add('selected')
    }
    selected = document.querySelectorAll('img.selected')
    list = []
    for (i=0; i<selected.length; i++) {
        list.push(selected[i].title)
    }
    sessionStorage.setItem('canvasList', JSON.stringify(list))
}
