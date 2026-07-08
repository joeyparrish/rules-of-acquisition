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

function openSearch(event) {
  event.preventDefault();
  searchDialog.classList.add('shown');
  document.getElementById('searchInput').focus();
}

function closeSearch(event) {
  if (event) event.preventDefault();
  searchDialog.classList.remove('shown');
  document.getElementById('searchInput').value = '';
  document.getElementById('searchResults').innerHTML = '';
}

// Returns matching [number, text] pairs for a query.
// Matches rule text (case-insensitive substring); a numeric query also
// matches rule numbers.
function searchRules(query) {
  query = query.trim().toLowerCase();
  if (!query) {
    return [];
  }
  const isNumeric = /^\d+$/.test(query);
  return window.rulesData.filter(function(entry) {
    const number = entry[0];
    const text = entry[1];
    if (text.toLowerCase().indexOf(query) !== -1) {
      return true;
    }
    if (isNumeric && String(number).indexOf(query) !== -1) {
      return true;
    }
    return false;
  });
}

// Re-renders the results list from the current query.
function renderSearch() {
  const results = document.getElementById('searchResults');
  const query = document.getElementById('searchInput').value;
  const matches = searchRules(query);
  results.innerHTML = '';
  if (!matches.length) {
    // Show a hint when the user typed something with no matches, but stay
    // blank for an empty query (e.g. right after opening the overlay).
    if (query.trim()) {
      const empty = document.createElement('div');
      empty.className = 'search-empty';
      empty.textContent = 'No results.';
      results.appendChild(empty);
    }
    return;
  }
  for (const entry of matches) {
    const number = entry[0];
    const text = entry[1];
    const row = document.createElement('div');
    row.className = 'search-result';
    row.textContent = number + '. ' + text;
    row.onclick = function() {
      go(number);
      closeSearch();
    };
    results.appendChild(row);
  }
}

// Escape closes the overlay; Enter jumps to the first result.
function onSearchKey(event) {
  if (event.key === 'Escape') {
    closeSearch();
  } else if (event.key === 'Enter') {
    const matches = searchRules(document.getElementById('searchInput').value);
    if (matches.length) {
      go(matches[0][0]);
      closeSearch();
    }
  }
}
