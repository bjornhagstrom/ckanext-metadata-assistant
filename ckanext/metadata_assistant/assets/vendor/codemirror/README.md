# CodeMirror 5 (vendored)

The text editor used for the description suggestion (changes shown inside the text being edited).

- Version: 5.65.18, from the npm package `codemirror@5.65.18`.
- Licence: MIT, see `LICENSE` (Marijn Haverbeke and others).
- `codemirror.css` is `lib/codemirror.css` of the package, unchanged (sha256 `eb494ea972d2661ef86f7f6ac656dd6786d721e49c9c1b46e1eb967e4b6f9bf3`).
- `codemirror.min.js` is `lib/codemirror.js` (sha256 `aedc03cf5294adb8f68eed55f8845888aa0c403a6445b15f80a8666a1f540d78b`)
  minified with `esbuild@0.21.5 --minify --legal-comments=none` (sha256 of the result
  `eea48bc0a46ed5693621a2cd416ec61d82a5ad4e9950cf1f8f451f81ef867a3a`). No other change.

- `mark-selection.js` is `addon/selection/mark-selection.js` of the package, unchanged (sha256 `5b9c6a0031fe895641f2eb2198df2592ec769a6685d6bb10f3f9b92a7822e286`). It adds the option `styleSelectedText`, so selected text can be coloured over the green of added words.

Version 5 is in maintenance. It was chosen because it ships as one ready file and needs no build step;
CodeMirror 6 (modular, actively developed, better accessibility) is the planned upgrade if this works well.
Without the library the panel falls back to a plain text box with the list of changes below it.
