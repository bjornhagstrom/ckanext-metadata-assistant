# Changelog

All notable changes to this project will be documented in this file. The format
is based on Keep a Changelog, and the project follows Semantic Versioning.

## [0.1.0] - 2026-11-20

The first public release.

### Added

- **A review panel in CKAN's dataset form.** A rule check without AI (required and recommended fields, themes outside the
  vocabulary, short descriptions, duplicate keywords, a missing licence, address slips, missing or outdated translations,
  and more), under its own heading and run again as the form changes; and, optionally, AI suggestions for the title,
  description, keywords and theme, each applied by the editor or not at all.
- **Translation suggestions** for title, description and keywords into the schema's other languages (ckanext-fluent),
  in the form and in bulk (`propose-translations`), stored as proposals that an editor reads and applies.
- **The portal's own languages:** labels, help texts and theme labels given per language follow the page's language and
  the portal's main language (`ckan.locale_default`), and landing pages are asked for in the metadata's language; no language is
  preferred by default.
- **Landing pages as material:** the portal fetches a public https page itself (or the AI service does, for models that
  can), summarises it once and reuses the summary; a page that was not used says why.
- **Administration pages** for sysadmins: the check settings with a setup check (including the landing page field and
  the AI connection), the instructions to the AI (editable, with a trial on a dataset), a catalogue-wide overview of
  what the rules find, and the translation proposals page for editors.
- **Background jobs and limits** for many editors at once: a worker (`ckan metadata-assistant worker`), queues, limits
  per user and site, and a breaker for a failing AI service; without a worker the requests run in the web request.
- **Commands:** `doctor`, `worker`, `queue`, `review-all`, `propose-translations`, `migrate-multilingual` and
  `migrate-ai-settings`.
- **The AI connection through [ckanext-ai-connector](https://github.com/bjornhagstrom/ckanext-ai-connector)** (`>=0.1,<0.2`),
  shared with other extensions: model, key, own AI server and time limits are set there. A review or translation that
  fails says why (the service busy, too slow, or out of quota).
- English source texts with a Swedish catalogue (`sv`, `sv_SE`).

### Upgrading from a development version

Development versions kept their AI settings under this extension's own names. `ckan metadata-assistant
migrate-ai-settings [--dry-run]` copies them to ckanext-ai-connector once, and `--remove-old` removes the old rows; the
setup check says when something still waits. See the README, "Upgrading from the settings this extension had".
