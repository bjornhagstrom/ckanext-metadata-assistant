'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  applySuggestion, formDraft, requestHeaders, fluentBaseName, applyTranslation,
  pendingSuggestionsText, suggestionDisplayText,
  shouldWarnAboutLandingPage, t, setStrings, STRINGS, hasTranslationTargets, capitalize,
  landingPageExtractKey, snapshotsEqual, firstErrorMessage, currentFieldText, withEditedValue,
  isBlankSuggestion, hasPendingEdit, newKeywordsOnly, orderSets, scrollDeltaToReveal, autosize, diffWords, diffSummary,
  unusedSuggestionButtons, showToast, linkParts, mdWrap, mdPrefixLines, mdCycleHeading, mdLink, diffChanges, revertChange, orderLikeTheForm, codeMirrorBox, visibleRemoved, autoCheckNeeded
} = require('../../assets/js/review.js');

function formWith(field) {
  return {
    querySelector(selector) {
      return selector === '[name="' + field.name + '"]' ? field : null;
    }
  };
}

// Kept in sync with flashField() in review.js.
const FLASH_CLASS = 'metadata-assistant-review__field-flash';

// Minimal stand-in for a form control. Since 2026-09-09 applySuggestion no
// longer moves focus -- it flashes the field instead -- so the stub needs a
// classList, an offsetWidth (read to force a reflow) and addEventListener.
function basicField(name) {
  const classes = new Set();
  return {
    name,
    value: '',
    events: [],
    listeners: [],
    offsetWidth: 0,
    classList: {
      add(value) { classes.add(value); },
      remove(value) { classes.delete(value); },
      contains(value) { return classes.has(value); }
    },
    addEventListener(type) { this.listeners.push(type); },
    dispatchEvent(event) { this.events.push(event.type); }
  };
}

test('applies a title and emits form events', () => {
  const field = basicField('title');
  assert.equal(applySuggestion(formWith(field), {
    field: 'title', suggested_value: 'Kommunala badplatser'
  }), true);
  assert.equal(field.value, 'Kommunala badplatser');
  assert.deepEqual(field.events, ['input', 'change']);
  assert.equal(field.classList.contains(FLASH_CLASS), true);
  assert.deepEqual(field.listeners, ['animationend']);
});

test('applies keyword arrays as a comma-separated fallback value', () => {
  const field = basicField('tag_string');
  assert.equal(applySuggestion(formWith(field), {
    field: 'tag_string', suggested_value: ['badplats', 'friluftsliv']
  }), true);
  assert.equal(field.value, 'badplats, friluftsliv');
  assert.deepEqual(field.events, ['input', 'change']);
  assert.equal(field.classList.contains(FLASH_CLASS), true);
});

test('adds suggested keywords to the existing ones, without duplicates', () => {
  const field = basicField('tag_string');
  field.value = 'badplats, Strand';
  assert.equal(applySuggestion(formWith(field), {
    field: 'tag_string', suggested_value: ['strand', 'friluftsliv', 'bad']
  }), true);
  assert.equal(field.value, 'badplats, Strand, friluftsliv, bad');
  assert.deepEqual(field.events, ['input', 'change']);
});

test('adds keywords given as a comma-separated string', () => {
  const field = basicField('tag_string');
  field.value = 'badplats';
  applySuggestion(formWith(field), { field: 'tag_string', suggested_value: 'friluftsliv, bad' });
  assert.equal(field.value, 'badplats, friluftsliv, bad');
});

test('selects only suggested controlled themes', () => {
  const field = basicField('theme');
  field.options = [
    { value: 'theme:ENVI', selected: false },
    { value: 'theme:SOCI', selected: true }
  ];
  assert.equal(applySuggestion(formWith(field), {
    field: 'theme', suggested_value: ['theme:ENVI']
  }), true);
  assert.deepEqual(field.options.map(option => option.selected), [true, false]);
  assert.deepEqual(field.events, ['input', 'change']);
  assert.equal(field.classList.contains(FLASH_CLASS), true);
});

test('does not report success when the field is absent', () => {
  assert.equal(applySuggestion({ querySelector() { return null; } }, {
    field: 'notes', suggested_value: 'Text'
  }), false);
});

test('serializes form controls without requiring the FormData API', () => {
  const form = { elements: [
    { name: '_csrf_token', value: 'ignored', type: 'hidden' },
    { name: 'title', value: 'Badplatser', type: 'text' },
    { name: 'theme', type: 'select-multiple', multiple: true, options: [
      { value: 'theme:ENVI', selected: true },
      { value: 'theme:SOCI', selected: false }
    ] },
    { name: 'private', value: 'true', type: 'checkbox', checked: true },
    { name: 'unused', value: 'x', type: 'checkbox', checked: false }
  ] };
  assert.deepEqual(formDraft(form), {
    title: 'Badplatser', theme: 'theme:ENVI', private: 'true'
  });
});

test('adds the form CSRF token to action API requests', () => {
  const form = {
    querySelector(selector) {
      return selector === 'input[name="_csrf_token"]' ? { value: 'test-token' } : null;
    }
  };
  assert.deepEqual(requestHeaders(form), {
    'Content-Type': 'application/json',
    'X-CSRFToken': 'test-token'
  });
});

test('warns only when the landing page was actually attempted and failed', () => {
  // The provider tried to read the page and could not.
  assert.equal(shouldWarnAboutLandingPage({ landing_page_used: false }), true);

  // It read the page.
  assert.equal(shouldWarnAboutLandingPage({ landing_page_used: true }), false);

  // Not applicable: no page supplied, or the provider has no managed fetch.
  // These must stay silent -- a falsy check would warn on every review.
  assert.equal(shouldWarnAboutLandingPage({ landing_page_used: null }), false);
  assert.equal(shouldWarnAboutLandingPage({}), false);
  assert.equal(shouldWarnAboutLandingPage({ landing_page_used: undefined }), false);

  // Defensive: never throw on a malformed payload.
  assert.equal(shouldWarnAboutLandingPage(null), null);
});

test('the landing page notice tells the editor what to do next', () => {
  assert.match(t('landing_page_notice'), /could not be read/);
  assert.match(t('landing_page_notice'), /form/);
  assert.match(t('landing_page_notice'), /again/);
});

test('a review taken while the page is still being read counts as stale', () => {
  // The landing page read takes 40-90s, so the editor can easily trigger a
  // review before it lands. When it does, the review must be redone -- that
  // is enforced by the extract key being part of the snapshot.
  const draft = { title: 'Smultron', notes: '', tag_string: '', theme: [], language: 'sv', url: 'https://example.org/p' };

  const reading = { url: 'https://example.org/p', status: 'reading', extract: null };
  const before = Object.assign({}, draft, { __extract: landingPageExtractKey(reading) });

  const ready = { url: 'https://example.org/p', status: 'ready', extract: { summary: 'x' } };
  const after = Object.assign({}, draft, { __extract: landingPageExtractKey(ready) });

  // Identical draft, different basis -> not equal -> the review re-runs.
  assert.equal(snapshotsEqual(before, after), false);

  // A failed read must ALSO invalidate it, or the editor would be left with
  // a provisional review and no second attempt.
  const failed = { url: 'https://example.org/p', status: 'failed', extract: null };
  const afterFailure = Object.assign({}, draft, { __extract: landingPageExtractKey(failed) });
  assert.equal(snapshotsEqual(before, afterFailure), false);

  // Once settled, an unchanged draft must NOT re-run -- that is the whole
  // point of keeping the number of AI calls down.
  assert.equal(snapshotsEqual(after, Object.assign({}, after)), true);
});

test('the extract key distinguishes read, unread and given-up', () => {
  assert.equal(landingPageExtractKey({ url: 'https://a/', status: 'idle', extract: null }), '');
  assert.equal(landingPageExtractKey({ url: 'https://a/', status: 'reading', extract: null }), '');
  assert.equal(landingPageExtractKey({ url: 'https://a/', status: 'failed', extract: null }), 'none');
  assert.equal(landingPageExtractKey({ url: 'https://a/', status: 'ready', extract: { summary: 'x' } }), 'https://a/');
  assert.equal(landingPageExtractKey(null), '');
});

// ckanext-fluent (2026-09-27): one input per language.
function fluentForm(fields) {
  return {
    elements: fields,
    querySelector(selector) {
      const exact = /^\[name="(.+)"\]$/.exec(selector);
      if (exact) return fields.find((f) => f.name === exact[1]) || null;
      const prefix = /^\[name\^="(.+)"\]$/.exec(selector);
      if (prefix) return fields.find((f) => f.name.startsWith(prefix[1])) || null;
      return null;
    }
  };
}

test('fluent base names', () => {
  assert.equal(fluentBaseName('title_translated-sv'), 'title');
  assert.equal(fluentBaseName('notes_translated-en'), 'notes');
  assert.equal(fluentBaseName('title'), null);
});

test('a fluent form draft is read under the plain field name, main language first', () => {
  const sv = Object.assign(basicField('title_translated-sv'), { value: 'Badplatser' });
  const en = Object.assign(basicField('title_translated-en'), { value: 'Bathing sites' });
  const draft = formDraft(fluentForm([sv, en]));
  assert.equal(draft.title, 'Badplatser');
  assert.equal(draft['title_translated-en'], 'Bathing sites');
});

test('a suggestion goes into the main-language fluent input', () => {
  const sv = basicField('title_translated-sv');
  const en = Object.assign(basicField('title_translated-en'), { value: 'Unchanged' });
  assert.equal(applySuggestion(fluentForm([sv, en]), {
    field: 'title', suggested_value: 'Kommunala badplatser'
  }), true);
  assert.equal(sv.value, 'Kommunala badplatser');
  assert.equal(en.value, 'Unchanged');
});

test('a translation goes into the English box only', () => {
  const sv = Object.assign(basicField('title_translated-sv'), { value: 'Badplatser' });
  const en = basicField('title_translated-en');
  assert.equal(applyTranslation(fluentForm([sv, en]), {
    field: 'title', target_field: 'title_translated', language: 'en',
    suggested_value: 'Bathing sites'
  }), true);
  assert.equal(en.value, 'Bathing sites');
  assert.equal(sv.value, 'Badplatser');
  assert.deepEqual(en.events, ['input', 'change']);
});

test('translated keywords are added to the English keywords already there', () => {
  const en = Object.assign(basicField('keywords_en-en'), { value: 'swimming, Beach' });
  applyTranslation(fluentForm([en]), {
    field: 'tag_string', target_field: 'keywords_en', language: 'en',
    suggested_value: ['beach', 'bathing site']
  });
  assert.equal(en.value, 'swimming, Beach, bathing site');
});

test('a missing English box is reported, not guessed', () => {
  const sv = basicField('title_translated-sv');
  assert.equal(applyTranslation(fluentForm([sv]), {
    field: 'title', target_field: 'title_translated', language: 'en', suggested_value: 'X'
  }), false);
  assert.equal(sv.value, '');
});

test('the notice says how many suggestions are left to review', () => {
  assert.equal(pendingSuggestionsText(3), '3 AI suggestions to review');
});

test('the page language replaces the English texts, key by key', () => {
  const saved = Object.assign({}, STRINGS);
  try {
    setStrings({ pending_suggestions: '{count} AI-förslag att granska', unknown: '' });
    assert.equal(pendingSuggestionsText(2), '2 AI-förslag att granska');
    assert.equal(t('use_suggestion'), 'Use suggestion');   // not translated: English
  } finally {
    Object.keys(STRINGS).forEach((key) => { STRINGS[key] = saved[key]; });
  }
});

test('a theme suggestion shows the name from the form, not the URI', () => {
  const gove = 'http://publications.europa.eu/resource/authority/data-theme/GOVE';
  const form = formWith({ name: 'theme', options: [
    { value: gove, text: ' Regeringen och den offentliga sektorn ' }] });
  assert.equal(suggestionDisplayText(form, { field: 'theme', suggested_value: [gove] }),
    'Regeringen och den offentliga sektorn');
  assert.equal(suggestionDisplayText(form, { field: 'theme', suggested_value: ['okänd'] }), 'okänd');
  assert.equal(suggestionDisplayText(form, { field: 'tag_string', suggested_value: ['a', 'b'] }), 'a, b');
});

test('the translate button needs an input for one of the target languages', () => {
  const form = { querySelector: (selector) => selector === '[name$="-fi"]' ? {} : null };
  assert.equal(hasTranslationTargets(form, ['en', 'fi']), true);
  assert.equal(hasTranslationTargets(form, ['en']), false);
  assert.equal(hasTranslationTargets(form, []), false);
  assert.equal(capitalize('svenska'), 'Svenska');
});

test('firstErrorMessage finds the message whatever field it is filed under', () => {
  assert.equal(firstErrorMessage({ ai: ['AI is off'], __type: 'Validation Error' }), 'AI is off');
  assert.equal(
    firstErrorMessage({ 'ckanext.metadata_assistant.schema_file': ['Config option not set.'], __type: 'Validation Error' }),
    'Config option not set.');
  assert.equal(firstErrorMessage({ translation: ['No target'] }), 'No target');
  assert.equal(firstErrorMessage({ __type: 'Validation Error' }), '');
  assert.equal(firstErrorMessage(undefined), '');
});

test('currentFieldText reads a text box or the selected options of a list', () => {
  const text = { name: 'title', value: 'Polisens händelser Malmö' };
  const list = { name: 'theme', options: [
    { value: 'a', text: ' Miljö ', selected: true }, { value: 'b', text: 'Ekonomi', selected: false },
    { value: '', text: 'Choose', selected: true }] };
  const form = { querySelector: (selector) => ({ '[name="title"]': text, '[name="theme"]': list })[selector] || null };
  assert.equal(currentFieldText(form, 'title'), 'Polisens händelser Malmö');
  assert.equal(currentFieldText(form, 'theme'), 'Miljö');
  assert.equal(currentFieldText(form, 'missing'), '');
});

test('withEditedValue keeps a list a list and a text a text', () => {
  const keywords = withEditedValue({ field: 'tag_string', suggested_value: ['a', 'b'], reason: 'r' }, ' karta, geodata ,, ');
  assert.deepEqual(keywords.suggested_value, ['karta', 'geodata']);
  assert.equal(keywords.reason, 'r');
  assert.equal(withEditedValue({ field: 'title', suggested_value: 'x' }, 'Händelser och stationer').suggested_value,
               'Händelser och stationer');
});

test('an emptied suggestion is blank, so it is not applied over the field', () => {
  assert.equal(isBlankSuggestion({ suggested_value: '  ' }), true);
  assert.equal(isBlankSuggestion({ suggested_value: [] }), true);
  assert.equal(isBlankSuggestion({ suggested_value: 'Titel' }), false);
  assert.equal(isBlankSuggestion({ suggested_value: ['a'] }), false);
});

test('hasPendingEdit sees text the editor changed in a suggestion box, not an untouched one', () => {
  const box = (value, original) => ({ value, getAttribute: () => original, closest: () => null });
  const container = (boxes) => ({ querySelectorAll: () => boxes });
  assert.equal(hasPendingEdit(container([box('Same', 'Same')])), false);
  assert.equal(hasPendingEdit(container([box('Same', 'Same'), box('Edited', 'Original')])), true);
  assert.equal(hasPendingEdit(container([])), false);
});

test('newKeywordsOnly leaves out keywords the dataset already has, and nothing when none is new', () => {
  const s = (value) => ({ field: 'tag_string', suggested_value: value, reason: 'r' });
  assert.deepEqual(newKeywordsOnly('geodata, Nyckelkodsområde', s(['nyckelkodsområde', 'kartlager', 'Kartlager'])).suggested_value,
                   ['kartlager']);
  assert.equal(newKeywordsOnly('a, b', s('A, b')), null);
  assert.equal(newKeywordsOnly('a', s('b, c')).suggested_value, 'b, c');
  const title = { field: 'title', suggested_value: 'y' };
  assert.equal(newKeywordsOnly('x', title), title);   // a different title is kept
});

test('orderSets puts the chosen box first and keeps the rest in order', () => {
  assert.deepEqual(orderSets([3, 2, 1], 1), [1, 3, 2]);
  assert.deepEqual(orderSets([3, 2, 1], 3), [3, 2, 1]);
  assert.deepEqual(orderSets([5], 5), [5]);
});

test('scrollDeltaToReveal keeps the buttons in view and does not scroll when everything already is', () => {
  // Buttons at 120px, the box heading at 300px, window 800px high: nothing to do.
  assert.equal(scrollDeltaToReveal(120, 300, 800), 0);
  // The box is far below the window: bring the buttons up near the top, not the box into the middle.
  assert.equal(scrollDeltaToReveal(900, 1100, 800), 884);
  // The editor scrolled past the buttons: scroll back up to them.
  assert.equal(scrollDeltaToReveal(-400, -250, 800), -416);
  // Buttons in view but the box is below the window's lower part.
  assert.equal(scrollDeltaToReveal(500, 780, 800), 484);
});

test('autosize makes a text box as tall as its text', () => {
  const box = { style: {}, scrollHeight: 240 };
  autosize(box);
  assert.equal(box.style.height, '240px');
  assert.equal(box.style.overflowY, 'hidden');
  const empty = { style: {}, scrollHeight: 0 };
  autosize(empty);   // not laid out yet: left at its natural height
  assert.equal(empty.style.height, 'auto');
  autosize(null);    // nothing to do, no error
});

test('diffWords shows what was added at the end of an otherwise unchanged text', () => {
  const ops = diffWords('Data om luften i Malmö.', 'Data om luften i Malmö. Mäts varje timme.');
  assert.deepEqual(ops.map((o) => o.type), ['eq', 'add']);
  assert.equal(ops[0].text, 'Data om luften i Malmö.');
  assert.equal(ops[1].text, ' Mäts varje timme.');
  assert.deepEqual(diffSummary(ops), { added: 3, removed: 0 });
});

test('diffWords shows a replaced word as removed and added, and keeps the rest', () => {
  const ops = diffWords('Polisens händelser i Malmö', 'Händelser i Malmö');
  const joined = (type) => ops.filter((o) => o.type === type).map((o) => o.text).join('|');
  assert.equal(joined('del'), 'Polisens händelser');
  assert.equal(joined('add'), 'Händelser');
  assert.deepEqual(diffSummary(ops), { added: 1, removed: 2 });
});

test('diffWords of equal texts is one unchanged run, and of an empty original is all added', () => {
  assert.deepEqual(diffWords('Samma text', 'Samma text'), [{ type: 'eq', text: 'Samma text' }]);
  assert.deepEqual(diffWords('', 'Ny text'), [{ type: 'add', text: 'Ny text' }]);
  assert.deepEqual(diffWords('Gammal', ''), [{ type: 'del', text: 'Gammal' }]);
  assert.deepEqual(diffSummary(diffWords('', 'a b c')), { added: 3, removed: 0 });
});

test('diffWords reproduces both texts when the unchanged and changed parts are put back together', () => {
  const oldText = 'Mätningar av partiklar PM10 i luften.\nDe görs varje timme av två stationer.';
  const newText = 'Mätningar av partiklar PM10 i luften.\nDe görs varje dygn av tre stationer i staden.';
  const ops = diffWords(oldText, newText);
  assert.equal(ops.filter((o) => o.type !== 'add').map((o) => o.text).join(''), oldText);
  assert.equal(ops.filter((o) => o.type !== 'del').map((o) => o.text).join(''), newText);
});

test('diffWords is not fooled by punctuation stuck to a word', () => {
  const ops = diffWords('Pumpar i staden', 'Pumpar i staden. Fler detaljer finns här.');
  assert.deepEqual(ops.map((o) => o.type), ['eq', 'add']);
  assert.equal(ops[0].text, 'Pumpar i staden');
  assert.deepEqual(diffSummary(ops), { added: 4, removed: 0 });
});

test('hasPendingEdit counts an edit in a box that is hidden by the Changes tab, but not in a used suggestion', () => {
  const box = (value, original, used) => ({ value, getAttribute: () => original, hidden: true, closest: () => (used ? {} : null) });
  const container = (boxes) => ({ querySelectorAll: () => boxes });
  assert.equal(hasPendingEdit(container([box('Edited', 'Original', false)])), true);
  assert.equal(hasPendingEdit(container([box('Edited', 'Original', true)])), false);
});

// --- the Markdown toolbar's text editing, on a stand-in for a text box (no browser: the fallback path) ---
function fakeBox(value, from, to) {
  return {
    value, selectionStart: from, selectionEnd: to === undefined ? from : to, events: 0,
    focus() {},
    setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b; },
    setRangeText(text, a, b) { this.value = this.value.slice(0, a) + text + this.value.slice(b); },
    dispatchEvent() { this.events += 1; },
  };
}
const selected = (box) => box.value.slice(box.selectionStart, box.selectionEnd);

test('bold wraps the selection, keeps it selected, and takes the marks off again', () => {
  const box = fakeBox('Hello world', 6, 11);
  mdWrap(box, '**');
  assert.equal(box.value, 'Hello **world**');
  assert.equal(selected(box), 'world');
  mdWrap(box, '**');
  assert.equal(box.value, 'Hello world');
  assert.equal(selected(box), 'world');
  assert.ok(box.events >= 2);   // the page is told the text changed
});

test('bold with nothing selected writes a placeholder and selects it', () => {
  const box = fakeBox('', 0);
  mdWrap(box, '**');
  assert.equal(box.value, '**text**');
  assert.equal(selected(box), 'text');
});

test('italic inside bold adds a mark instead of taking the bold off', () => {
  const box = fakeBox('**x**', 2, 3);
  mdWrap(box, '*');
  assert.equal(box.value, '***x***');
});

test('a bulleted list is added to every touched line and removed when they all have it', () => {
  const box = fakeBox('first\nsecond\n\nthird', 0, 12);
  const bullets = (row) => '- ' + row;
  mdPrefixLines(box, /^\s*[-*+]\s+/, bullets);
  assert.equal(box.value, '- first\n- second\n\nthird');
  box.setSelectionRange(0, box.value.indexOf('\n\nthird'));
  mdPrefixLines(box, /^\s*[-*+]\s+/, bullets);
  assert.equal(box.value, 'first\nsecond\n\nthird');
});

test('a numbered list counts the lines, skipping blank ones', () => {
  const box = fakeBox('a\n\nb\nc', 0, 6);
  mdPrefixLines(box, /^\s*\d+[.)]\s+/, (row, n) => n + '. ' + row);
  assert.equal(box.value, '1. a\n\n2. b\n3. c');
});

test('the heading button goes second level, third level, then none', () => {
  const box = fakeBox('Rubrik\nText', 2);
  mdCycleHeading(box);
  assert.equal(box.value, '## Rubrik\nText');
  mdCycleHeading(box);
  assert.equal(box.value, '### Rubrik\nText');
  mdCycleHeading(box);
  assert.equal(box.value, 'Rubrik\nText');
});

test('the link button makes the selection the link text and selects the address to type over', () => {
  const box = fakeBox('Se sidan nu', 3, 8);
  mdLink(box);
  assert.equal(box.value, 'Se [sidan](https://) nu');
  assert.equal(selected(box), 'https://');
  const empty = fakeBox('', 0);
  mdLink(empty);
  assert.equal(empty.value, '[text](https://)');
});

// --- the changes list: where each change sits, taking one back, and the order of the suggestions ---
const SIX = 'Ett två tre fyra fem sex sju åtta nio tio elva tolv';

test('diffChanges merges changes that lie close together and keeps them apart when they do not', () => {
  const original = 'Alfa beta gamma delta epsilon zeta eta theta iota kappa lambda my';
  const suggested = 'Alfa BETA gamma delta epsilon zeta eta theta iota kappa lambda MY';
  const apart = diffChanges(original, suggested);
  assert.equal(apart.length, 2);
  assert.deepEqual(apart.map((c) => [c.removed, c.added]), [['beta', 'BETA'], ['my', 'MY']]);
  assert.equal(diffChanges('a b c d', 'A b c D').length, 1);   // two unchanged words between: one change
});

test('diffChanges gives each change its place in the current text and a little context', () => {
  const [change] = diffChanges('Detta är en text om luft.', 'Detta är en längre text om luft.');
  assert.equal(change.removed, '');
  assert.equal(change.added, 'längre ');
  assert.equal('Detta är en längre text om luft.'.slice(change.start, change.start + change.added.length), 'längre ');
  assert.ok(change.before.includes('en') && change.after.includes('text'));
});

test('taking one change back leaves the others in place, and the text can be rebuilt change by change', () => {
  const original = 'Alfa beta gamma delta epsilon zeta eta theta iota kappa lambda my';
  const suggested = 'Alfa BETA gamma delta epsilon zeta eta theta iota kappa lambda MY';
  const box = fakeBox(suggested, 0);
  revertChange(box, diffChanges(original, suggested)[0]);
  assert.equal(box.value, 'Alfa beta gamma delta epsilon zeta eta theta iota kappa lambda MY');
  revertChange(box, diffChanges(original, box.value)[0]);   // the list is made again from the box, as in the page
  assert.equal(box.value, original);
});

test('taking back an addition removes it, and taking back a deletion puts the text back', () => {
  const added = fakeBox('Se Ny Text här', 0);
  revertChange(added, diffChanges('Se här', added.value)[0]);
  assert.equal(added.value, 'Se här');
  const removed = fakeBox('Se här', 0);
  revertChange(removed, diffChanges('Se gamla texten här', removed.value)[0]);
  assert.equal(removed.value, 'Se gamla texten här');
});

test('the suggestions come in the order of the fields in the form, whatever order they arrived in', () => {
  const at = (n) => ({ n, compareDocumentPosition(other) { return other.n > n ? 4 : 2; } });
  const controls = { title: at(1), notes: at(2), tag_string: at(3) };
  const form = { querySelector: (selector) => controls[(/name="([^"]+)"/.exec(selector) || [])[1]] || null };
  const sorted = orderLikeTheForm(form, [{ field: 'tag_string' }, { field: 'notes' }, { field: 'title' }]);
  assert.deepEqual(sorted.map((s) => s.field), ['title', 'notes', 'tag_string']);
});

test('suggestions for fields the form does not have keep a fixed order, after those it has', () => {
  const form = { querySelector: () => null };
  const sorted = orderLikeTheForm(form, [{ field: 'theme' }, { field: 'tag_string' }, { field: 'title' }, { field: 'notes' }]);
  assert.deepEqual(sorted.map((s) => s.field), ['title', 'notes', 'tag_string', 'theme']);
});

// --- CodeMirror behind the same members as a text box: the editing functions work on either ---
function fakeCodeMirror(text, from, to) {
  const cm = {
    text, from, to: to === undefined ? from : to, handlers: {},
    getValue() { return this.text; }, setValue(value) { this.text = value; },
    getCursor(which) { return { ch: which === 'from' ? this.from : this.to }; },
    indexFromPos(pos) { return pos.ch; }, posFromIndex(index) { return { ch: index }; },
    setSelection(a, b) { this.from = a.ch; this.to = b.ch; },
    replaceRange(value, a, b) { this.text = this.text.slice(0, a.ch) + value + this.text.slice(b.ch); },
    focus() {}, on(type, handler) { this.handlers[type] = handler; },
  };
  return cm;
}

test('the CodeMirror stand-in lets the editing functions work through CodeMirror, with no browser insert', () => {
  const cm = fakeCodeMirror('Hello world', 6, 11);
  const box = codeMirrorBox(cm);
  assert.equal(box.value, 'Hello world');
  assert.equal(box.selectionStart, 6);
  assert.equal(box.selectionEnd, 11);
  mdWrap(box, '**');
  assert.equal(cm.text, 'Hello **world**');
  assert.deepEqual([cm.from, cm.to], [8, 13]);   // the word stays selected
  mdWrap(box, '**');
  assert.equal(cm.text, 'Hello world');
});

test('taking a change back works the same through the CodeMirror stand-in', () => {
  const original = 'Alfa beta gamma delta epsilon zeta eta theta iota kappa lambda my';
  const suggested = 'Alfa BETA gamma delta epsilon zeta eta theta iota kappa lambda MY';
  const cm = fakeCodeMirror(suggested, 0);
  const box = codeMirrorBox(cm);
  revertChange(box, diffChanges(original, box.value)[1]);
  assert.equal(cm.text, 'Alfa BETA gamma delta epsilon zeta eta theta iota kappa lambda my');
});

test('the stand-in passes key presses and changes on to CodeMirror, and shortcuts reach the editing function', () => {
  const cm = fakeCodeMirror('abc', 0, 3);
  const box = codeMirrorBox(cm);
  mdWrap(box, '*');
  assert.equal(cm.text, '*abc*');
  let seen = 0;
  box.addEventListener('input', () => { seen += 1; });
  cm.handlers.change();
  assert.equal(seen, 1);
  let key = null;
  box.addEventListener('keydown', (event) => { key = event.key; });
  cm.handlers.keydown(cm, { key: 'b' });
  assert.equal(key, 'b');
});

test('line endings are not changes: a stored \\r\\n text against the editor\'s \\n text has none', () => {
  const stored = 'Första raden.  \r\n\r\n## Rubrik  \r\nSlut';
  const inEditor = 'Första raden.  \n\n## Rubrik  \nSlut';
  assert.deepEqual(diffChanges(stored, inEditor), []);
});

test('a change in white space only is not listed, but a real change next to one is', () => {
  assert.deepEqual(diffChanges('en text  \nmed rad', 'en text\n\nmed rad'), []);
  const changes = diffChanges('en text  \nmed rad', 'en längre text\n\nmed rad');
  assert.equal(changes.length, 1);
  assert.equal(changes[0].added, 'längre ');
});

test('removed text with a line break is shown with a symbol, not as an empty line', () => {
  assert.equal(visibleRemoved('rad ett\nrad två'), 'rad ett \u21B5 rad två');
  assert.equal(visibleRemoved('a  \r\n\r\nb'), 'a \u21B5 b');
  assert.equal(visibleRemoved(' '), '\u2423');          // a lone removed space gets a symbol, not an invisible mark
  assert.equal(visibleRemoved('\n'), '\u21B5');
  assert.equal(visibleRemoved('ingen radbrytning'), 'ingen radbrytning');
});

test('trailing spaces added or taken away at the end of a line are not changes, but a space between words is', () => {
  // The case from the editor: markdown's two trailing spaces were removed by the suggestion.
  const original = 'Anläggningar för idrott.  \n\n## Resurs  \n__Attribut__  \n';
  const suggestion = 'Anläggningar för idrott.\n\n## Resurs\n__Attribut__\n';
  assert.deepEqual(diffChanges(original, suggestion), []);
  assert.deepEqual(diffChanges(suggestion, original), []);
  // Two words joined is a change an editor can see.
  const joined = diffChanges('ett två tre', 'ett tvåtre');
  assert.equal(joined.length, 1);
});

test('an automatic review is only needed when something differs from what the page opened with or the last review saw', () => {
  const opened = { title: 'Utegym', notes: 'Kort text.', tag_string: '', theme: '', language: '', url: 'https://x.se', __extract: '' };
  const edited = Object.assign({}, opened, { title: 'Utegym och spår' });
  assert.equal(autoCheckNeeded(opened, null, opened), false);          // left a field, changed nothing
  assert.equal(autoCheckNeeded(edited, null, opened), true);           // changed the title
  assert.equal(autoCheckNeeded(edited, edited, opened), false);        // already reviewed with this text
  assert.equal(autoCheckNeeded(opened, edited, opened), true);         // changed back after a review: differs from what it saw
  const empty = { title: '', notes: '', tag_string: '', theme: '', language: '', url: '', __extract: '' };
  assert.equal(autoCheckNeeded(empty, null, null), false);             // nothing to review
  const withPage = Object.assign({}, opened, { __extract: 'https://x.se' });
  assert.equal(autoCheckNeeded(withPage, null, opened), true);         // the landing page was read: one review follows
});

// --- AI requests as jobs --------------------------------------------------------------------------------
{
  const { postJob, progressText } = require('../../assets/js/review.js');
  const jobsTest = require('node:test');

  function fakeFetch(answers, seen) {
    return async (url, options) => {
      const action = url.split('/').pop();
      seen.push({ action, body: JSON.parse(options.body) });
      const next = answers[action].shift();
      if (next instanceof Error) throw next;
      return { json: async () => next };
    };
  }

  jobsTest('a request answered at once is returned in the shape of an API answer', async () => {
    const seen = [];
    global.fetch = fakeFetch({ metadata_assistant_job_start: [
      { success: true, result: { state: 'done', result: { suggestions: [] }, cached: true, prepared_at: '2026-10-11T10:00:00Z' } }] }, seen);
    const outcome = await postJob('review', { id: 'x', cache_only: true }, null);
    assert.deepEqual(outcome, { success: true, result: { suggestions: [] }, cached: true, prepared_at: '2026-10-11T10:00:00Z' });
    assert.equal(seen[0].body.kind, 'review');
    assert.equal(seen[0].body.cache_only, true);
  });

  jobsTest('nothing prepared is success with none', async () => {
    global.fetch = fakeFetch({ metadata_assistant_job_start: [{ success: true, result: { state: 'none' } }] }, []);
    assert.deepEqual(await postJob('review', {}, null), { success: true, none: true });
  });

  jobsTest('a queued job is followed until it is done, and the position is reported', async () => {
    const seen = [], progress = [];
    global.fetch = fakeFetch({
      metadata_assistant_job_start: [{ success: true, result: { state: 'queued', job_id: 'j1', position: 2 } }],
      metadata_assistant_job_status: [
        { success: true, result: { state: 'queued', position: 1 } },
        { success: true, result: { state: 'running' } },
        { success: true, result: { state: 'done', result: { summary: 'ok' } } }]
    }, seen);
    const realTimeout = global.setTimeout;
    global.setTimeout = (fn) => realTimeout(fn, 0);
    try {
      const outcome = await postJob('review', {}, null, (job) => progress.push(job.state + ':' + (job.position || '')));
      assert.equal(outcome.success, true);
      assert.deepEqual(outcome.result, { summary: 'ok' });
    } finally { global.setTimeout = realTimeout; }
    assert.deepEqual(progress, ['queued:2', 'queued:1', 'running:']);
    assert.equal(seen[1].body.job_id, 'j1');
  });

  jobsTest('a failed job and a refused start both come back as errors with the message', async () => {
    global.fetch = fakeFetch({ metadata_assistant_job_start: [
      { success: true, result: { state: 'failed', error: 'The AI is tired.' } },
      { success: false, error: { ai: ['Daily limit.'] } }] }, []);
    assert.deepEqual(await postJob('review', {}, null), { success: false, error: { ai: ['The AI is tired.'] } });
    assert.equal(firstErrorMessage((await postJob('review', {}, null)).error), 'Daily limit.');
  });

  jobsTest('a lost connection is tried again, then reported', async () => {
    global.fetch = fakeFetch({
      metadata_assistant_job_start: [{ success: true, result: { state: 'queued', job_id: 'j1' } }],
      metadata_assistant_job_status: [new Error('x'), new Error('x'), new Error('x')]
    }, []);
    const realTimeout = global.setTimeout;
    global.setTimeout = (fn) => realTimeout(fn, 0);
    try {
      const outcome = await postJob('review', {}, null);
      assert.equal(outcome.success, false);
      assert.equal(firstErrorMessage(outcome.error), STRINGS.job_lost);
    } finally { global.setTimeout = realTimeout; }
  });

  jobsTest('progress text shows the place in line, and the running text once it runs', () => {
    const text = progressText('Reviewing…');
    assert.equal(text({ state: 'queued', position: 3 }), 'Waiting in line: 3 before you…');
    assert.equal(text({ state: 'queued' }), 'Waiting for a free place…');
    assert.equal(text({ state: 'running' }), 'Reviewing…');
  });
}

{
  const { postJob: pj } = require('../../assets/js/review.js');
  require('node:test')('a job that is gone says so', async () => {
    global.fetch = async (url) => ({ json: async () => url.endsWith('job_start') ?
      { success: true, result: { state: 'queued', job_id: 'j' } } :
      { success: false, error: { __type: 'Not Found Error', message: 'Gone.' } } });
    const realTimeout = global.setTimeout;
    global.setTimeout = (fn) => realTimeout(fn, 0);
    try {
      const outcome = await pj('review', {}, null);
      assert.equal(firstErrorMessage(outcome.error), 'Gone.');
    } finally { global.setTimeout = realTimeout; }
  });
}

{
  const { ageText } = require('../../assets/js/review.js');
  require('node:test')('the age of the downloaded copy is given in the largest fitting unit', () => {
    const now = new Date('2026-10-12T12:00:00Z');
    assert.match(ageText('2026-10-12T11:59:40Z', now), /0 minutes|this minute|now/);
    assert.match(ageText('2026-10-12T09:00:00Z', now), /3 hours ago/);
    assert.match(ageText('2026-10-10T12:00:00Z', now), /2 days ago/);
    assert.equal(ageText('nonsense', now), '');
  });
}

test('a title or description identical to the current one is not suggested', () => {
  const same = { field: 'notes', suggested_value: 'A  text.\n' };
  assert.equal(newKeywordsOnly('A text.', same), null);
  assert.notEqual(newKeywordsOnly('A text.', { field: 'notes', suggested_value: 'A longer text.' }), null);
  assert.equal(newKeywordsOnly('Roads', { field: 'title', suggested_value: 'Roads' }), null);
});

{
  const { rulesSummary } = require('../../assets/js/review.js');
  require('node:test')('the completeness line counts what to fix and tips', () => {
    assert.equal(rulesSummary([]), 'Completeness: nothing to remark on.');
    assert.equal(rulesSummary([{ severity: 'warning' }, { severity: 'error' }, { severity: 'info' }]),
                 'Completeness: 2 to fix, 1 tips');
    assert.equal(rulesSummary([{ severity: 'info' }]), 'Completeness: 1 tips');
  });
}

test('says what differs between an address and the better one offered', () => {
  const { addressChanges } = require('../../assets/js/review.js');
  assert.deepEqual(addressChanges('http://www.w3.org/TR/vocab-dcat-2', 'https://www.w3.org/TR/vocab-dcat-2/'), ['https', 'slash_added']);
  assert.deepEqual(addressChanges('https://a.se/x/', 'https://a.se/x'), ['slash_removed']);
  assert.deepEqual(addressChanges('https://a.se/x', 'https://www.a.se/x'), ['www_added']);
  assert.deepEqual(addressChanges('http://www.a.se/x', 'https://a.se/x'), ['https', 'www_removed']);
  assert.deepEqual(addressChanges('http://a.se/x', 'https://b.se/y'), ['other']);
  assert.deepEqual(addressChanges('http://a.se/x?q=1', 'https://a.se/x?q=2'), ['other']);
});

test('unusedSuggestionButtons: only the buttons that are still enabled (a used suggestion has a disabled one)', () => {
  const buttons = [{ disabled: false }, { disabled: true }, { disabled: false }];
  const root = { querySelectorAll: (selector) => { assert.equal(selector, '.metadata-assistant-review__apply'); return buttons; } };
  assert.deepEqual(unusedSuggestionButtons(root), [buttons[0], buttons[2]]);
  assert.deepEqual(unusedSuggestionButtons({ querySelectorAll: () => [] }), []);
});

test('showToast: one notice, shown at once, hidden after the time (a second call reuses it)', () => {
  const made = [];
  const doc = {
    body: { appendChild: (el) => made.push(el) },
    querySelector: () => made[0] || null,
    createElement: () => ({ attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, addEventListener() {}, hidden: true })
  };
  const realSet = global.setTimeout, realClear = global.clearTimeout;
  let fire = null;
  global.setTimeout = (fn) => { fire = fn; return 1; };
  global.clearTimeout = () => {};
  try {
    const toast = showToast('hello', doc, 6);
    assert.equal(toast.textContent, 'hello');
    assert.equal(toast.hidden, false);
    assert.equal(toast.attrs.role, 'status');
    assert.equal(showToast('again', doc), toast);
    assert.equal(made.length, 1);
    assert.equal(toast.textContent, 'again');
    fire();
    assert.equal(toast.hidden, true);
  } finally { global.setTimeout = realSet; global.clearTimeout = realClear; }
});

test('linkParts: web addresses become links, trailing punctuation stays outside, plain text and HTML stay text', () => {
  assert.deepEqual(linkParts('See https://github.com/x/y. Then go on'), [
    { text: 'See ', href: '' }, { text: 'https://github.com/x/y', href: 'https://github.com/x/y' }, { text: '. Then go on', href: '' }]);
  assert.deepEqual(linkParts('no address <b>here</b>'), [{ text: 'no address <b>here</b>', href: '' }]);
  assert.deepEqual(linkParts(''), []);
  assert.deepEqual(linkParts('(https://a.se/b)'), [{ text: '(', href: '' }, { text: 'https://a.se/b', href: 'https://a.se/b' }, { text: ')', href: '' }]);
});
