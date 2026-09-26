# 0008 — Scripts run under a CSP nonce: no inline handlers

## Context

The Content-Security-Policy allows scripts that carry the request's nonce
(`script-src 'self' 'nonce-…'`), set in `vcs/web/hooks.py`. A nonce authorises
`<script>` blocks only. An `onclick=` attribute is not authorised by it, and a
browser that sees a nonce ignores `'unsafe-inline'` — so an inline handler is
a button that silently does nothing.

## Decision

- No `on*=` attributes. Behaviour is attached from `static/behaviors.js`:
  `data-vzh` with `VZ.bind()`, or `data-vz-act` with `VZ.action()`.
- Every inline `<script>` carries `nonce="{{ csp_nonce }}"`; the nonce comes
  from a context processor that touches nothing but `g`, so even the 500 page
  has it.
- Inline `style=` only for a value the server computes, or for an element a
  script reveals with `el.style.display = ''` — clearing an inline style
  cannot unhide an element a class hides.

## Consequences

Front-end changes go through the stylesheet and `behaviors.js`. The style
rule is a ratchet: the count of inline styles may only go down.

## Held by

`tests/test_no_inline_handlers.py`; `tests/test_inline_styles.py`; the browser
tier's CSP-violation check (`tests/test_browser.py`).
