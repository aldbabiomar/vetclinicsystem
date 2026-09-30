// Copy buttons, and showing either the days or the date field for a license's length.
document.querySelectorAll('[data-copy]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var el = document.getElementById(btn.getAttribute('data-copy'));
    var text = el.textContent.trim();
    function done() { btn.textContent = 'Copied'; setTimeout(function () { btn.textContent = 'Copy'; }, 1500); }
    function select() {
      var r = document.createRange(); r.selectNodeContents(el);
      var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
      btn.textContent = 'Selected';
    }
    try { navigator.clipboard.writeText(text).then(done, select); } catch (e) { select(); }
  });
});

document.querySelectorAll('[data-length]').forEach(function (group) {
  function show() {
    var mode = group.querySelector('input[name=length]:checked').value;
    group.querySelectorAll('[data-for]').forEach(function (el) { el.hidden = el.getAttribute('data-for') !== mode; });
  }
  group.querySelectorAll('input[name=length]').forEach(function (r) { r.addEventListener('change', show); });
  show();
});
