// Change the page and the URL, without affecting browser history.
function go(pageNumber) {
  history.replaceState(null, '', '#' + (pageNumber || ''));

  const input = document.getElementById('i' + pageNumber);
  if (input) {
    input.checked = true;
  }
}

function goRandom() {
  const index = Math.floor(Math.random() * extantRules.length);
  go(extantRules[index]);
}

// Only called on explicit URL bar changes and on page load.
// Loads the page called for by the URL change.
function onhashchange() {
  if (location.hash) {
    const pageNumber = parseInt(location.hash.substr(1), 10);
    go(pageNumber);
  }
}

document.addEventListener('DOMContentLoaded', onhashchange);
window.addEventListener('hashchange', onhashchange);

function sponsor(event) {
  event.preventDefault();
  sponsorDialog.classList.add('shown');
  return false;
}

function unsponsor(event) {
  event.preventDefault();
  sponsorDialog.classList.remove('shown');
  return false;
}
