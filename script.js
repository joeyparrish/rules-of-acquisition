(() => {
  function onhashchange() {
    if (location.hash) {
      const pageNumber = parseInt(location.hash.substr(1), 10);
      const input = document.getElementById('i' + pageNumber);
      if (input) {
        input.checked = true;
      }
    }
  }

  document.addEventListener('DOMContentLoaded', onhashchange);
  window.addEventListener('hashchange', onhashchange);
})();
