/*
 * VZMoney — the browser half of money.py, for LIVE PREVIEWS only (the POS
 * total and change, a boarding stay's suggested total, a refund's running
 * total). The server recomputes and validates every figure on submit; this
 * exists so the number a person sees before pressing the button is the
 * number they will be charged.
 *
 * Same rules as money.py, same inputs: base.html emits the clinic's money
 * setting as window.VZ_MONEY = {code, minorUnits, cashUnit, quantum,
 * phoneCountryCode, phoneLocalLength}, or null before one is chosen.
 *
 *   IQ — whole dinars, cash unit 250: totals round to the nearest note, a
 *        real bill never rounds down to free, change rounds DOWN to a note.
 *   JO — three decimals, cash unit 0.001: the same rules change nothing.
 *
 * Digits follow the page language exactly as the server's |money filter does:
 * Arabic-Indic in Arabic, Western otherwise — digits only, never the
 * separators. Never write a converted value back into an <input>.
 */
(function (global) {
  "use strict";

  var cfg = global.VZ_MONEY || null;
  var ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";

  function num(x) {
    x = Number(x);
    return isFinite(x) ? x : 0;
  }
  function unit() { return cfg ? Number(cfg.cashUnit) : 0.001; }
  function places() { return cfg ? cfg.minorUnits : 3; }
  // Storage scale (0.001), which also absorbs binary floating-point noise.
  function tidy(x) { return Number(num(x).toFixed(3)); }

  function roundCash(x, mode) {
    x = num(x);
    if (x === 0) return 0;
    var u = unit();
    var q = x / u;
    // Half-up for "nearest"; floor for "down". The 1e-9 keeps an exact
    // multiple that float division lands just below from dropping a unit.
    q = mode === "down" ? Math.floor(q + 1e-9) : Math.floor(q + 0.5 + 1e-9);
    return tidy(q * u);
  }

  function payable(raw, discountPct) {
    raw = num(raw);
    if (raw === 0) return 0;
    var u = unit();
    if (raw > 0 && raw <= u / 2 && num(discountPct) < 100) return tidy(u);
    return roundCash(raw, "nearest");
  }

  function changeDue(received, total) {
    return Math.max(roundCash(num(received) - num(total), "down"), 0);
  }

  function localizeDigits(s) {
    if ((document.documentElement.getAttribute("lang") || "").indexOf("ar") !== 0) return s;
    return String(s).replace(/[0-9]/g, function (d) { return ARABIC_DIGITS.charAt(Number(d)); });
  }

  function format(x) {
    var p = places();
    return localizeDigits(num(x).toLocaleString("en-US", {
      minimumFractionDigits: p, maximumFractionDigits: p,
    }));
  }

  global.VZMoney = {
    config: cfg,
    chosen: !!cfg,
    cashUnit: unit,
    places: places,
    roundCash: roundCash,
    payable: payable,
    changeDue: changeDue,
    format: format,
    localizeDigits: localizeDigits,
  };
})(window);
