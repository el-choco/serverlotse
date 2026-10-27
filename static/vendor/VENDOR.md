# Terminal assets

Vendored from the official npm registry, distribution SHA-512 integrity verified:
- @xterm/xterm 6.0.0 (MIT), lib/xterm.js and css/xterm.css
- @xterm/addon-fit 0.11.0 (MIT), lib/addon-fit.js

Upstream licenses are included. No CDN requests at runtime.
Local change to xterm.js: the four style-element creation sites use
__slTerminalStyle(document), which attaches the current HTML response's
terminal-style-nonce. No global DOM patch; no unsafe-inline CSP policy.
Retain this adaptation when upgrading. Remove source maps not shipped here if needed;
missing maps only affect optional browser debugging.
