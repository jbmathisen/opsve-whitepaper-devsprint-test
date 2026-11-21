// Visa/dölj kommentarer, och växla mellan textalternativ i kommentarerna.
(function () {
  var KEY = 'os-mock-notes';
  var btn = document.getElementById('toggle-notes');
  function set(on) {
    document.body.classList.toggle('hide-notes', !on);
    if (btn) { btn.setAttribute('aria-pressed', on ? 'true' : 'false'); btn.textContent = on ? 'Kommentarer: på' : 'Kommentarer: av'; }
    try { localStorage.setItem(KEY, on ? '1' : '0'); } catch (e) {}
  }
  var start = true;
  try { start = localStorage.getItem(KEY) !== '0'; } catch (e) {}
  set(start);
  if (btn) btn.addEventListener('click', function () { set(document.body.classList.contains('hide-notes')); });

  // Knappar med data-target och data-text byter text i ett element.
  document.querySelectorAll('[data-swap]').forEach(function (group) {
    var target = document.getElementById(group.getAttribute('data-swap'));
    var buttons = group.querySelectorAll('button');
    buttons.forEach(function (b) {
      b.addEventListener('click', function () {
        target.innerHTML = b.getAttribute('data-html');
        buttons.forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
      });
    });
  });
})();
