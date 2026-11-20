/* Show rule findings and optional AI suggestions without submitting the form. */
(function () {
  'use strict';

  // Interface texts (2026-10-01). English is the source language; the panel
  // passes the translations for the page's language as JSON in data-i18n
  // (see review_panel.html, where every key must also be listed).
  var STRINGS = {
    severity_error: 'Error',
    severity_warning: 'Needs review',
    severity_info: 'Information',
    rules_no_findings: 'The rule-based review found no problems.',
    field_title: 'Title',
    field_notes: 'Description',
    field_tag_string: 'Keywords',
    field_theme: 'Theme',
    landing_page_notice: 'The landing page could not be read this time, so the review is based only on what is in the form. Run the review again if you want the page to be taken into account.',
    translation_heading: 'Suggested translations',
    translation_note: 'Machine-translated – review each suggestion before you use it. Nothing is saved until you save the dataset.',
    translation_source: '{language} (original)',
    translation_value: 'Suggestion ({language})',
    translation_applied_label: '{field} ({language})',
    translation_applied: 'The translation has been added to the form. Check it before you save.',
    translation_field_missing: 'The field for the translation could not be found in the form.',
    translation_language_failed: 'No suggestions in {language}: {error}',
    translation_running: 'AI is translating title, description and keywords…',
    translation_failed: 'The translation could not be completed.',
    translation_failed_retry: 'The translation could not be completed. Try again.',
    translation_done: 'The translation suggestions are ready.',
    translation_nothing: 'There was nothing to translate.',
    use_suggestion: 'Use suggestion',
    unused_message: 'You have AI suggestions that are not used. What should happen to them?',
    unused_save: 'Use the suggestions and save',
    unused_discard: 'Discard the suggestions and save',
    unused_back: 'Back to the form',
    compare_current: 'Current value',
    compare_empty: '(empty)',
    compare_proposal: 'Suggestion – you can edit it before you use it',
    compare_proposal_add: 'Suggestion, added to the current keywords – you can edit it before you use it',
    compare_choice_note: 'Themes are chosen in the list in the form.',
    edit_kept: 'You have edited a suggestion, so the suggestions were not refreshed. Use it, or run the review again when you are done.',
    ai_nothing: 'The AI found nothing to change in this dataset. Run the review again for a second opinion.',
    set_ai: 'AI suggestions',
    set_translation: 'Translations',
    set_top: 'Move to top',
    choice_new: 'Get new suggestions',
    diff_edit: 'Edit',
    diff_preview: 'Preview',
    diff_summary: '{added} words added, {removed} removed',
    diff_none: 'No changes from the current text.',
    changes_heading: 'Changes from the current text ({count})',
    show_removed: 'Show removed text',
    keep_original: 'Keep the original',
    use_whole: 'Use the whole suggestion again',
    preview_loading: 'Preparing the preview…',
    preview_failed: 'The preview could not be made.',
    set_replaced: 'New suggestions from {time} replaced the ones from {old}.',
    replace_edited: 'You have edited a suggestion. Replace the suggestions anyway?',
    md_toolbar: 'Format the text',
    md_bold: 'Bold',
    md_italic: 'Italic',
    md_heading: 'Heading',
    md_bullets: 'Bulleted list',
    md_numbers: 'Numbered list',
    md_quote: 'Quote',
    md_link: 'Link',
    compare_blank: 'The suggestion is empty. Write a value, or leave the field as it is.',
    suggestion_used: 'Suggestion used',
    toast_not_saved: 'Added to the form, but not saved yet. Save the dataset to keep the change.',
    suggestion_applied: 'The suggestion for {field} has been added to the form. Check the content before you save.',
    suggestion_field_missing: 'The field could not be found in the form. The suggestion has not been used.',
    pending_suggestions: '{count} AI suggestions to review',
    questions_heading: 'Questions to consider',
    rules_running: 'Checking completeness…',
    rules_status_ok: 'Completeness: nothing to remark on.',
    rules_status: 'Completeness: {summary}',
    rules_fix: '{count} to fix',
    rules_tips: '{count} tips',
    rules_failed: 'The completeness check could not be run.',
    rules_failed_contact: 'The completeness check could not be run. Try again or contact an administrator.',
    address_hint_forwards: 'This address forwards to {address}.',
    address_hint_https: 'This address also works over https: {address}',
    address_hint_why_forwards: 'The quality check of the European data portal only counts links that answer directly, so the address it forwards to is the safer choice.',
    address_hint_why_https: 'Plain http is not secure, and the link may stop working when the site only allows https. https also avoids a forward, which the quality check of the European data portal does not count.',
    address_change_heading: 'What changes:',
    address_change_https: 'http becomes https',
    address_change_slash_added: 'a slash is added at the end',
    address_change_slash_removed: 'the slash at the end is removed',
    address_change_www_added: 'www is added',
    address_change_www_removed: 'www is removed',
    address_change_other: 'the address leads to another place, so check that it is the right page',
    address_hint_use: 'Use this address',
    address_hint_used: 'The address in the form has been changed. Check it before you save.',
    reading_landing_page: 'Reading the landing page… the review starts when it is done.',
    busy_landing_page: 'AI is reading the landing page…',
    busy_reviewing: 'AI is reviewing the metadata…',
    ai_updating: 'AI is generating suggestions…',
    ai_running: 'AI is reviewing title, description, keywords and theme…',
    ai_failed: 'The AI review could not be completed.',
    ai_failed_detail: 'The AI review could not be completed: {error}',
    ai_heading: 'AI suggestions',
    ai_done: 'The AI review is complete. Read and assess the suggestions before you change anything.',
    landing_age: 'Landing page downloaded {age}.',
    flow_landing_reading: 'Downloading the landing page…',
    flow_landing_needs_https: 'The landing page is only read over https, and this address starts with http://. Change it to the https address to let the AI read the page.',
    flow_landing_use_https: 'Use the https address and read the page',
    flow_landing_failed: 'The landing page could not be downloaded. The AI uses only the texts in the form.',
    landing_notice_failed: 'The landing page was not used: {reason} The AI uses only the texts in the form.',
    landing_notice_failed_plain: 'The landing page could not be read. The AI uses only the texts in the form.',
    landing_retry: 'Try again',
    flow_landing_none: 'No landing page address: the AI uses only the texts in the form.',
    flow_ai_running: 'AI is analysing…',
    flow_ai_done: 'AI suggestions are ready.',
    flow_ai_failed: 'The AI analysis did not succeed.',
    flow_review: 'Read the suggestions and use the ones you want. Nothing is saved until you save the dataset.',
    reread_no_url: 'There is no landing page address in the form.',
    job_queued: 'Waiting for a free place…',
    job_queued_position: 'Waiting in line: {count} before you…',
    job_timeout: 'The AI did not answer in time. Try again.',
    job_lost: 'The connection was lost. Try again.',
    prepared_at: 'Suggestions prepared {time}. Press the button for new ones.'
  };

  function t(key, params) {
    var text = STRINGS[key] || key;
    Object.keys(params || {}).forEach(function (name) {
      text = text.split('{' + name + '}').join(String(params[name]));
    });
    return text;
  }

  // The first message of a CKAN validation error, whatever field it is filed under
  // (ai, translation, or a config option such as ckanext.metadata_assistant.schema_file).
  function firstErrorMessage(error) {
    if (!error) return '';
    var keys = Object.keys(error);
    for (var i = 0; i < keys.length; i++) {
      if (keys[i].charAt(0) === '_' || keys[i] === 'message') continue;
      var value = [].concat(error[keys[i]])[0];
      if (typeof value === 'string' && value) return value;
    }
    return '';
  }

  function setStrings(translations) {
    Object.keys(translations || {}).forEach(function (key) {
      if (translations[key]) STRINGS[key] = translations[key];
    });
  }

  function formDraft(form) {
    var draft = {};
    function add(key, value) {
      if (key === '_csrf_token' || key === '_ckan_phase' || key === 'save') return;
      if (Object.prototype.hasOwnProperty.call(draft, key)) {
        if (!Array.isArray(draft[key])) draft[key] = [draft[key]];
        draft[key].push(value);
      } else draft[key] = value;
    }
    Array.prototype.forEach.call(form.elements || [], function (field) {
      var key = field.name;
      if (!key || field.disabled || ['submit', 'button', 'file'].indexOf(field.type) !== -1) return;
      if ((field.type === 'checkbox' || field.type === 'radio') && !field.checked) return;
      if (field.multiple && field.options) {
        Array.prototype.forEach.call(field.options, function (option) {
          if (option.selected) add(key, option.value);
        });
        return;
      }
      add(key, field.value);
    });
    // ckanext-fluent: one input per language, named e.g. "title_translated-sv"
    // and "title_translated-en". The review works on the first language in
    // the form (the site's main language), under the plain field name the
    // rest of this module and the server use.
    Object.keys(draft).forEach(function (key) {
      var base = fluentBaseName(key);
      if (base && draft[base] === undefined) draft[base] = draft[key];
    });
    return draft;
  }

  // "title_translated-sv" -> "title"; anything else -> null.
  function fluentBaseName(name) {
    var match = /^(.+)_translated-[a-z]{2,8}$/.exec(name || '');
    return match ? match[1] : null;
  }

  // The form control for a field: the plain one, or with ckanext-fluent the
  // first language's input (the form lists the main language first).
  function fieldControl(form, name) {
    return form.querySelector('[name="' + name + '"]') ||
      form.querySelector('[name^="' + name + '_translated-"]');
  }

  function severityLabel(severity) {
    return t({ error: 'severity_error', warning: 'severity_warning' }[severity] || 'severity_info');
  }

  // One line for the completeness check: what has to be fixed (errors and warnings) and tips (information).
  function rulesSummary(findings) {
    var fix = 0, tips = 0;
    (findings || []).forEach(function (f) { if (f.severity === 'info') tips++; else fix++; });
    if (!fix && !tips) return t('rules_status_ok');
    var parts = [];
    if (fix) parts.push(t('rules_fix', { count: fix }));
    if (tips) parts.push(t('rules_tips', { count: tips }));
    return t('rules_status', { summary: parts.join(', ') });
  }

  function renderResults(container, findings, onUseAddress) {
    container.textContent = '';
    container.hidden = false;
    if (!findings.length) {
      var success = document.createElement('p');
      success.className = 'alert alert-success';
      success.textContent = t('rules_no_findings');
      container.appendChild(success);
      return;
    }
    var list = document.createElement('ul');
    list.className = 'metadata-assistant-review__list';
    findings.forEach(function (finding) {
      var item = document.createElement('li');
      item.className = 'metadata-assistant-review__finding metadata-assistant-review__finding--' + finding.severity;
      var heading = document.createElement('strong');
      heading.textContent = severityLabel(finding.severity) + (finding.label || finding.field ? ': ' + (finding.label || finding.field) : '');
      var message = document.createElement('span');
      appendLinked(message, finding.message);
      item.appendChild(heading);
      item.appendChild(message);
      if (finding.suggestion && onUseAddress) {
        var apply = document.createElement('button');
        apply.type = 'button';
        apply.className = 'btn btn-primary btn-sm metadata-assistant-review__use-address';
        apply.textContent = t('address_hint_use');
        apply.addEventListener('click', function () {
          if (onUseAddress(finding)) {
            apply.disabled = true;
            apply.textContent = t('address_hint_used');
          }
        });
        item.appendChild(apply);
      }
      list.appendChild(item);
    });
    container.appendChild(list);
  }

  function fieldLabel(field) {
    return STRINGS['field_' + field] || field;
  }

  // What differs between an address and the better one the link check offers, as keys of address_change_* texts.
  function addressChanges(from, to) {
    var changes = [];
    var a = /^(https?):\/\/([^\/?#]*)([^?#]*)(.*)$/i.exec(String(from || '').trim());
    var b = /^(https?):\/\/([^\/?#]*)([^?#]*)(.*)$/i.exec(String(to || '').trim());
    if (!a || !b) return ['other'];
    var hostA = a[2].toLowerCase(), hostB = b[2].toLowerCase();
    var wwwA = hostA.indexOf('www.') === 0, wwwB = hostB.indexOf('www.') === 0;
    var samePage = hostA.replace(/^www\./, '') === hostB.replace(/^www\./, '') &&
      a[3].replace(/\/+$/, '') === b[3].replace(/\/+$/, '') && a[4] === b[4];
    if (!samePage) return ['other'];
    if (a[1].toLowerCase() === 'http' && b[1].toLowerCase() === 'https') changes.push('https');
    if (!wwwA && wwwB) changes.push('www_added');
    if (wwwA && !wwwB) changes.push('www_removed');
    var slashA = /\/$/.test(a[3]), slashB = /\/$/.test(b[3]);
    if (!slashA && slashB) changes.push('slash_added');
    if (slashA && !slashB) changes.push('slash_removed');
    return changes;
  }

  function suggestionText(value) {
    return Array.isArray(value) ? value.join(', ') : String(value || '');
  }

  // A theme is a URI; show the name the form's own list gives it.
  function suggestionDisplayText(form, suggestion) {
    var field = suggestion.field === 'theme' && form ? fieldControl(form, 'theme') : null;
    if (!field || !field.options) return suggestionText(suggestion.suggested_value);
    var values = Array.isArray(suggestion.suggested_value) ? suggestion.suggested_value : [suggestion.suggested_value];
    return values.map(function (uri) {
      var option = Array.prototype.filter.call(field.options, function (o) { return o.value === uri; })[0];
      return option ? option.text.trim() : String(uri);
    }).join(', ');
  }

  // The value a field has in the form now, as text, for the side-by-side view.
  function currentFieldText(form, name) {
    var control = form ? fieldControl(form, name) : null;
    if (!control) return '';
    if (control.options) {
      return Array.prototype.filter.call(control.options, function (o) { return o.selected && o.value; })
        .map(function (o) { return o.text.trim(); }).join(', ');
    }
    return String(control.value || '');
  }

  // A suggestion with the text the editor settled on: a list stays a list (split on commas).
  function withEditedValue(suggestion, text) {
    var edited = Object.assign({}, suggestion);
    edited.suggested_value = Array.isArray(suggestion.suggested_value) ?
      String(text || '').split(',').map(function (item) { return item.trim(); }).filter(Boolean) :
      String(text || '');
    return edited;
  }

  function isBlankSuggestion(suggestion) {
    var value = suggestion.suggested_value;
    return Array.isArray(value) ? value.length === 0 : !String(value || '').trim();
  }

  // --- A small Markdown toolbar for a text box --------------------------------------------------------
  // Plain DOM code with no framework. Edits go through the browser's own insert, so the box's undo keeps working; where
  // that is not allowed it sets the text and tells the page it changed.
  function mdEdit(el, from, to, text, selectFrom, selectTo) {
    el.focus();
    el.setSelectionRange(from, to);
    var done = false;
    if (!el.useDirectEdit && typeof document !== 'undefined' && typeof document.execCommand === 'function') {
      try { done = document.execCommand('insertText', false, text); } catch (e) { done = false; }
    }
    if (!done) {
      el.setRangeText(text, from, to, 'end');
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    el.setSelectionRange(selectFrom, selectTo);
  }

  // **bold** or *italic* around the selection; used again on the same text it takes the marks off.
  function mdWrap(el, mark, placeholder) {
    var from = el.selectionStart, to = el.selectionEnd, value = el.value;
    var chosen = value.slice(from, to);
    var around = value.slice(from - mark.length, from) === mark && value.slice(to, to + mark.length) === mark;
    // One star is italic and two are bold: a single star next to another is the other mark's, not ours.
    var single = mark.length === 1 && (value[from - 2] === mark || value[to + 1] === mark);
    if (around && !single) {
      mdEdit(el, from - mark.length, to + mark.length, chosen, from - mark.length, from - mark.length + chosen.length);
      return;
    }
    var inner = chosen || placeholder || 'text';
    mdEdit(el, from, to, mark + inner + mark, from + mark.length, from + mark.length + inner.length);
  }

  // The lines the selection touches, as a block of text to rewrite.
  function mdLines(el) {
    var from = el.selectionStart, to = el.selectionEnd, value = el.value;
    var start = value.lastIndexOf('\n', from - 1) + 1;
    var last = to > from && value[to - 1] === '\n' ? to - 1 : to;
    var found = value.indexOf('\n', last);
    var end = found < 0 ? value.length : found;
    return { start: start, end: end, rows: value.slice(start, end).split('\n') };
  }

  function mdPrefixLines(el, has, add) {
    var block = mdLines(el);
    var filled = block.rows.filter(function (row) { return row.trim(); });
    var off = filled.length > 0 && filled.every(function (row) { return has.test(row); });
    var n = 0;
    var next = block.rows.map(function (row) {
      if (!row.trim()) return row;
      n += 1;
      return off ? row.replace(has, '') : add(row, n);
    }).join('\n');
    mdEdit(el, block.start, block.end, next, block.start, block.start + next.length);
  }

  // No heading, then ## and ###, then none again: Markdown headings in a description are second level and up.
  function mdCycleHeading(el) {
    var block = mdLines(el);
    var first = block.rows[0];
    var match = /^(#{2,3})\s/.exec(first);
    var level = match ? match[1].length : 0;
    var bare = first.replace(/^#{1,6}\s+/, '');
    var next = level >= 3 ? bare : '#'.repeat(level ? level + 1 : 2) + ' ' + bare;
    mdEdit(el, block.start, block.start + first.length, next, block.start + next.length, block.start + next.length);
  }

  // [text](https://): the selection becomes the text and the address is selected for typing.
  function mdLink(el) {
    var from = el.selectionStart, to = el.selectionEnd;
    var text = el.value.slice(from, to) || 'text';
    var insert = '[' + text + '](https://)';
    var urlFrom = from + text.length + 3;
    mdEdit(el, from, to, insert, urlFrom, urlFrom + 8);
  }

  var MD_TOOLS = [
    { key: 'bold', icon: 'fa-bold', shortcut: 'B', run: function (el) { mdWrap(el, '**'); } },
    { key: 'italic', icon: 'fa-italic', shortcut: 'I', run: function (el) { mdWrap(el, '*'); } },
    { key: 'heading', icon: 'fa-header', run: mdCycleHeading },
    { key: 'bullets', icon: 'fa-list-ul', run: function (el) { mdPrefixLines(el, /^\s*[-*+]\s+/, function (row) { return '- ' + row; }); } },
    { key: 'numbers', icon: 'fa-list-ol', run: function (el) { mdPrefixLines(el, /^\s*\d+[.)]\s+/, function (row, n) { return n + '. ' + row; }); } },
    { key: 'quote', icon: 'fa-quote-left', run: function (el) { mdPrefixLines(el, /^\s*>\s?/, function (row) { return '> ' + row; }); } },
    { key: 'link', icon: 'fa-link', shortcut: 'K', run: mdLink }
  ];

  // The toolbar for a text box, and Ctrl/Cmd+B, I and K in the box itself.
  function buildMarkdownToolbar(box) {
    var bar = document.createElement('div');
    bar.className = 'metadata-assistant-review__toolbar';
    bar.setAttribute('role', 'toolbar');
    bar.setAttribute('aria-label', t('md_toolbar'));
    MD_TOOLS.forEach(function (tool) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-outline-secondary btn-sm';
      var label = t('md_' + tool.key);
      button.setAttribute('aria-label', label);
      button.title = tool.shortcut ? label + ' (Ctrl/Cmd+' + tool.shortcut + ')' : label;
      var icon = document.createElement('i');
      icon.className = 'fa ' + tool.icon;
      icon.setAttribute('aria-hidden', 'true');
      button.appendChild(icon);
      // Keep the box's selection: a click on a button must not move focus away from it first.
      button.addEventListener('mousedown', function (event) { event.preventDefault(); });
      button.addEventListener('click', function () { tool.run(box); });
      bar.appendChild(button);
    });
    box.addEventListener('keydown', function (event) {
      if (!(event.metaKey || event.ctrlKey) || event.shiftKey || event.altKey) return;
      var key = String(event.key || '').toLowerCase();
      var tool = MD_TOOLS.filter(function (candidate) { return candidate.shortcut && candidate.shortcut.toLowerCase() === key; })[0];
      if (!tool) return;
      event.preventDefault();
      event.stopPropagation();
      tool.run(box);
    });
    return bar;
  }

  // --- Changes against the original, word by word (2026-10-09) --------------------------------------------
  // Pure functions: the text is split into words and the spaces between them, the common start and end are
  // set aside and the rest is compared with a longest-common-subsequence table. Returns a list of
  // {type: 'eq'|'add'|'del', text}; adjacent runs of the same kind are merged.
  function tokenize(text) {
    // Words, runs of space and each punctuation mark on its own, so "staden." and "staden" share the word.
    return String(text || '').split(/(\s+|[^\p{L}\p{N}\s])/u).filter(function (part) { return part !== ''; });
  }

  function pushOp(ops, type, text) {
    if (!text) return;
    var last = ops[ops.length - 1];
    if (last && last.type === type) last.text += text; else ops.push({ type: type, text: text });
  }

  function diffWords(oldText, newText) {
    var a = tokenize(oldText), b = tokenize(newText);
    var start = 0;
    while (start < a.length && start < b.length && a[start] === b[start]) start++;
    var endA = a.length, endB = b.length;
    while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) { endA--; endB--; }
    var ops = [];
    pushOp(ops, 'eq', a.slice(0, start).join(''));
    var left = a.slice(start, endA), right = b.slice(start, endB);
    if (left.length * right.length > 4000000) {
      // Too big for the table: show the middle as replaced rather than make the page wait.
      pushOp(ops, 'del', left.join(''));
      pushOp(ops, 'add', right.join(''));
    } else {
      var m = left.length, n = right.length;
      var table = [];
      for (var i = 0; i <= m; i++) table.push(new Int32Array(n + 1));
      for (i = m - 1; i >= 0; i--) {
        for (var j = n - 1; j >= 0; j--) {
          table[i][j] = left[i] === right[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
        }
      }
      i = 0; j = 0;
      var removed = [], added = [];
      var flush = function () {
        pushOp(ops, 'del', removed.join(''));
        pushOp(ops, 'add', added.join(''));
        removed = []; added = [];
      };
      while (i < m || j < n) {
        if (i < m && j < n && left[i] === right[j]) { flush(); pushOp(ops, 'eq', left[i]); i++; j++; }
        else if (j < n && (i === m || table[i][j + 1] >= table[i + 1][j])) { added.push(right[j]); j++; }
        else { removed.push(left[i]); i++; }
      }
      flush();
    }
    pushOp(ops, 'eq', a.slice(endA).join(''));
    // A space alone between two changes is part of them, not a stretch of unchanged text.
    for (var k = 1; k < ops.length - 1; k++) {
      if (ops[k].type === 'eq' && /^\s+$/.test(ops[k].text) && ops[k - 1].type !== 'eq' && ops[k + 1].type !== 'eq') {
        var space = ops[k].text;
        ops[k] = { type: 'del', text: space };
        ops.splice(k + 1, 0, { type: 'add', text: space });
      }
    }
    var merged = [];
    ops.forEach(function (op) { pushOp(merged, op.type, op.text); });
    return merged;
  }

  function wordCount(text) {
    return (String(text || '').match(/[\p{L}\p{N}]+/gu) || []).length;
  }

  function diffSummary(ops) {
    var added = 0, removed = 0;
    ops.forEach(function (op) {
      if (op.type === 'add') added += wordCount(op.text);
      if (op.type === 'del') removed += wordCount(op.text);
    });
    return { added: added, removed: removed };
  }

  // The changes between the original and a text, as a list a person can act on. A change is a stretch that
  // was removed and/or added; changes with at most `gap` unchanged words between them are one change, so a
  // rewritten sentence is one item and not a dozen. Each change knows where it sits in the current text
  // (start, and the length of what was added), so it can be taken back there. `before` and `after` are a few
  // unchanged words around it, for orientation.
  var CONTEXT_WORDS = 5;

  function edgeWords(text, fromEnd) {
    var parts = tokenize(text);
    var picked = [], seen = 0;
    for (var i = 0; i < parts.length && seen < CONTEXT_WORDS; i++) {
      var part = fromEnd ? parts[parts.length - 1 - i] : parts[i];
      picked.push(part);
      if (/[\p{L}\p{N}]/u.test(part)) seen++;
    }
    return (fromEnd ? picked.reverse() : picked).join('');
  }

  // White space that was swapped for other white space (a line ending, trailing spaces), or a line break that
  // was only added or taken away, is not a change an editor can see or copy: it counts as unchanged. A lone
  // space between words is kept, since taking one away joins two words.
  // Spaces that sit at the end or start of a line (before or after a line break, or at the text's ends).
  function atLineEdge(before, next) {
    var last = before[before.length - 1];
    var beforeEdge = !last || (last.type === 'eq' && /\n$/.test(last.text));
    var afterEdge = !next || (next.type === 'eq' && /^\n/.test(next.text));
    return beforeEdge || afterEdge;
  }

  function withoutWhitespaceChanges(ops) {
    var blank = function (text) { return !String(text).trim(); };
    var cleaned = [];
    for (var i = 0; i < ops.length; i++) {
      var op = ops[i], next = ops[i + 1];
      if (op.type === 'del' && blank(op.text) && next && next.type === 'add' && blank(next.text)) {
        cleaned.push({ type: 'eq', text: next.text });
        i += 1;
      } else if (op.type !== 'eq' && blank(op.text) && (/\n/.test(op.text) || atLineEdge(cleaned, next))) {
        if (op.type === 'add') cleaned.push({ type: 'eq', text: op.text });
      } else {
        cleaned.push(op);
      }
    }
    var merged = [];
    cleaned.forEach(function (op) { pushOp(merged, op.type, op.text); });
    return merged;
  }

  function diffChanges(original, current, gap) {
    var limit = gap === undefined ? 3 : gap;
    // A text box and CodeMirror give the text with \n for every line break; the stored text may have \r\n.
    var ops = withoutWhitespaceChanges(diffWords(String(original || '').replace(/\r\n?/g, '\n'), current));
    var segments = [];
    ops.forEach(function (op, index) {
      var last = segments[segments.length - 1];
      if (op.type === 'eq') {
        var small = last && last.change && wordCount(op.text) <= limit && index < ops.length - 1;
        if (small) { last.removed += op.text; last.added += op.text; } else segments.push({ eq: op.text });
      } else if (last && last.change) {
        last[op.type === 'del' ? 'removed' : 'added'] += op.text;
      } else {
        segments.push({ change: true, removed: op.type === 'del' ? op.text : '', added: op.type === 'add' ? op.text : '' });
      }
    });
    var changes = [], position = 0;
    segments.forEach(function (segment, index) {
      if (!segment.change) { position += segment.eq.length; return; }
      // A change in white space only (a line break, a trailing space) is not one the editor can see or copy.
      if (!segment.removed.trim() && !segment.added.trim()) { position += segment.added.length; return; }
      var before = index > 0 ? segments[index - 1].eq || '' : '';
      var after = index < segments.length - 1 ? segments[index + 1].eq || '' : '';
      changes.push({ start: position, removed: segment.removed, added: segment.added,
                     before: edgeWords(before, true), after: edgeWords(after, false) });
      position += segment.added.length;
    });
    return changes;
  }

  // Removed text as shown: a line break is drawn as a symbol so it does not open an empty line.
  function visibleRemoved(text) {
    var value = String(text || '');
    // Only white space was removed: show what it was, so it is not an invisible mark.
    if (value && !value.trim()) return value.replace(/\r?\n/g, '\u21B5').replace(/[ \t]/g, '\u2423');
    return value.replace(/[ \t]*(?:\r?\n[ \t]*)+/g, ' \u21B5 ');
  }

  // Take one change back: what it added is replaced by what it removed (an edit the browser can undo).
  function revertChange(box, change) {
    var end = change.start + change.added.length;
    mdEdit(box, change.start, end, change.removed, change.start, change.start + change.removed.length);
  }

  // The suggestions in the order of the fields in the form above (the first control of each field), so they
  // always come the same way whatever order the AI answered in; fields not found go last in a fixed order.
  var FALLBACK_ORDER = ['title', 'notes', 'tag_string', 'theme'];

  function orderLikeTheForm(form, suggestions) {
    var rank = function (field) { var i = FALLBACK_ORDER.indexOf(field); return i < 0 ? FALLBACK_ORDER.length : i; };
    return suggestions.map(function (suggestion, index) {
      return { suggestion: suggestion, index: index, control: form ? fieldControl(form, suggestion.field) : null };
    }).sort(function (a, b) {
      if (a.control && b.control && a.control !== b.control) {
        return (a.control.compareDocumentPosition(b.control) & 4) ? -1 : 1;   // 4: b follows a
      }
      if (a.control && !b.control) return -1;
      if (!a.control && b.control) return 1;
      return rank(a.suggestion.field) - rank(b.suggestion.field) || a.index - b.index;
    }).map(function (entry) { return entry.suggestion; });
  }

  // A keyword suggestion is added to the current keywords, so keywords already there are left out;
  // null when nothing new is left.
  function newKeywordsOnly(currentText, suggestion) {
    // A title or description identical to what is there (blank space aside) changes nothing: not shown.
    if (suggestion.field === 'title' || suggestion.field === 'notes') {
      var same = function (text) { return String(text || '').replace(/\s+/g, ' ').trim(); };
      return same(currentText) === same(suggestion.suggested_value) ? null : suggestion;
    }
    if (suggestion.field !== 'tag_string') return suggestion;
    var have = {};
    String(currentText || '').split(',').forEach(function (word) { have[word.trim().toLowerCase()] = true; });
    var words = Array.isArray(suggestion.suggested_value) ? suggestion.suggested_value :
      String(suggestion.suggested_value || '').split(',');
    var seen = {};
    var fresh = words.map(function (word) { return String(word).trim(); }).filter(function (word) {
      var key = word.toLowerCase();
      if (!word || have[key] || seen[key]) return false;
      seen[key] = true;
      return true;
    });
    if (!fresh.length) return null;
    return Object.assign({}, suggestion, {
      suggested_value: Array.isArray(suggestion.suggested_value) ? fresh : fresh.join(', ') });
  }

  // --- Result boxes: every run is kept, the newest on top (2026-10-09). -------------------------
  // The ids of the boxes in the order they are shown, with ``top`` moved first.
  function orderSets(ids, top) {
    return [top].concat(ids.filter(function (id) { return id !== top; }));
  }

  function formatTime(date) {
    try { return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; }
  }

  // True while nothing in a box has been used or edited, so it may be replaced by a newer run.
  function isUntouched(set) {
    return !set.body.querySelector('.metadata-assistant-review__suggestion--applied') && !hasPendingEdit(set.body);
  }

  // How far to scroll so that the buttons row and the top of a result box are both in view: nothing when they
  // already are, else the buttons row goes near the top of the window (the boxes start right below it).
  function scrollDeltaToReveal(actionsTop, boxTop, viewportHeight, margin) {
    var m = margin === undefined ? 16 : margin;
    var buttonsVisible = actionsTop >= m - 1 && actionsTop < viewportHeight - 40;
    var boxVisible = boxTop >= 0 && boxTop <= viewportHeight - 60;
    return buttonsVisible && boxVisible ? 0 : Math.round(actionsTop - m);
  }

  // A clearer flash than a field's: the whole box lights up, so the editor sees where the suggestions are.
  function flashSet(element) {
    var flashClass = 'metadata-assistant-review__set-flash';
    element.classList.remove(flashClass);
    void element.offsetWidth;   // restart the animation if it is flashed again at once
    element.classList.add(flashClass);
    var clear = function () { element.classList.remove(flashClass); };
    element.addEventListener('animationend', clear, { once: true });
    setTimeout(clear, 2500);
  }

  function createResultStack(host, reveal) {
    var show = reveal || function (el) { el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); };
    var sets = [];
    var counter = 0;

    function refresh() {
      sets.forEach(function (set, index) { set.topButton.hidden = index === 0; });
    }

    function bringToTop(set) {
      var ids = orderSets(sets.map(function (s) { return s.id; }), set.id);
      sets = ids.map(function (id) { return sets.filter(function (s) { return s.id === id; })[0]; });
      host.insertBefore(set.element, host.firstChild);
      set.element.open = true;
      refresh();
    }

    function add(kind, title) {
      // One box per kind: a new run replaces the previous one (2026-10-10), and the box is lifted to the top.
      var existing = latest(kind);
      if (existing) {
        existing.previousTime = existing.time;
        existing.replaced = true;
        existing.body.textContent = '';
        existing.snapshot = null;
        existing.newButton.hidden = true;
        existing.stamp();
        bringToTop(existing);
        return existing;
      }
      counter += 1;
      var element = document.createElement('details');
      element.className = 'metadata-assistant-review__set';
      element.open = true;
      element.setAttribute('data-kind', kind);
      var summary = document.createElement('summary');
      summary.className = 'metadata-assistant-review__set-title';
      var name = document.createElement('strong');
      name.textContent = title;
      var time = document.createElement('time');
      var topButton = document.createElement('button');
      topButton.type = 'button';
      topButton.className = 'btn btn-link btn-sm metadata-assistant-review__set-top';
      topButton.textContent = t('set_top');
      topButton.hidden = true;
      // "Get new suggestions", to the right of the title; shown when a click found these still current.
      var newButton = document.createElement('button');
      newButton.type = 'button';
      newButton.className = 'btn btn-primary btn-sm metadata-assistant-review__set-new';
      newButton.textContent = t('choice_new');
      newButton.hidden = true;
      summary.appendChild(name);
      summary.appendChild(document.createTextNode(' '));
      summary.appendChild(time);
      summary.appendChild(topButton);
      summary.appendChild(newButton);
      var body = document.createElement('div');
      body.className = 'metadata-assistant-review__ai-results';
      element.appendChild(summary);
      element.appendChild(body);
      var set = { id: counter, kind: kind, element: element, body: body, snapshot: null, topButton: topButton, replaced: false,
                  newButton: newButton,
                  stamp: function () { time.textContent = formatTime(new Date()); set.time = time.textContent; } };
      set.stamp();
      topButton.addEventListener('click', function (event) {
        event.preventDefault();   // the button sits in the <summary>; do not fold the box
        event.stopPropagation();
        bringToTop(set);
        show(element);
      });
      newButton.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        newButton.hidden = true;
        if (set.run) set.run();
      });
      // A newer box of the same kind makes the offer to get new suggestions here pointless.
      sets.forEach(function (older) { if (older.kind === kind) older.newButton.hidden = true; });
      host.insertBefore(element, host.firstChild);
      sets.unshift(set);
      refresh();
      return set;
    }

    function latest(kind) {
      return sets.filter(function (s) { return s.kind === kind; })[0] || null;
    }

    // A click found these suggestions still current: lift them, make them noticed, offer to get new ones.
    function present(set, run) {
      bringToTop(set);
      set.run = run;
      set.newButton.hidden = false;
      show(set.element);
      flashSet(set.element);
    }

    function isTop(set) { return sets.length > 0 && sets[0] === set; }

    return { add: add, latest: latest, bringToTop: bringToTop, isTop: isTop, present: present, reveal: show };
  }

  // A text box as tall as its text, so a whole description is visible without scrolling.
  function autosize(box) {
    if (!box || !box.style) return;
    box.style.overflowY = 'hidden';
    box.style.height = 'auto';
    if (box.scrollHeight) box.style.height = box.scrollHeight + 'px';
  }

  function autosizeOnInput(box) {
    if (!box || !box.addEventListener) return;
    box.addEventListener('input', function () { autosize(box); });
    autosize(box);
  }

  // True when the editor has changed the text of a suggestion that is not used yet.
  function hasPendingEdit(container) {
    return Array.prototype.some.call(container.querySelectorAll('.metadata-assistant-review__edit'), function (box) {
      // A suggestion that has been used is done with; a hidden box (the Changes tab is showing) can still hold an edit.
      var used = box.closest && box.closest('.metadata-assistant-review__suggestion--applied');
      return !used && box.value !== box.getAttribute('data-original');
    });
  }

  // Set by initialize: the form the panel belongs to (its request headers), and whether descriptions are Markdown.
  var activeForm = null;
  var markdownEnabled = false;

  function renderPreview(text, target) {
    target.textContent = t('preview_loading');
    postAction('metadata_assistant_render_markdown', { text: text }, activeForm)
      .then(function (payload) {
        if (payload.success) target.innerHTML = payload.result.html;   // CKAN's own renderer: sanitised on the server
        else target.textContent = t('preview_failed');
      })
      .catch(function () { target.textContent = t('preview_failed'); });
  }

  // CodeMirror (assets/vendor/codemirror) behind the same few members the toolbar and the changes code use on a
  // text box, so one set of tested editing functions serves both. Edits go through CodeMirror itself, which keeps
  // its own undo history.
  function codeMirrorBox(cm) {
    return {
      useDirectEdit: true,
      get value() { return cm.getValue(); },
      set value(text) { cm.setValue(text); },
      get selectionStart() { return cm.indexFromPos(cm.getCursor('from')); },
      get selectionEnd() { return cm.indexFromPos(cm.getCursor('to')); },
      focus: function () { cm.focus(); },
      setSelectionRange: function (from, to) { cm.setSelection(cm.posFromIndex(from), cm.posFromIndex(to)); },
      setRangeText: function (text, from, to) { cm.replaceRange(text, cm.posFromIndex(from), cm.posFromIndex(to)); },
      dispatchEvent: function () {},
      addEventListener: function (type, listener) {
        if (type === 'keydown') cm.on('keydown', function (instance, event) { listener(event); });
        if (type === 'input') cm.on('change', function () { listener({}); });
      }
    };
  }

  // The original and the suggestion side by side. The suggestion is one text box with, below it, the changes
  // against the original as a list: what was added (green), what was removed (red, struck through; a tick box
  // hides it) and a button on each change to keep the original there instead. The list follows the box while the
  // editor types. Markdown descriptions also get a preview tab. Themes are chosen in the form's own list, so
  // they are shown, not edited.
  function buildCompare(options) {
    var wrap = document.createElement('div');
    wrap.className = 'metadata-assistant-review__compare';
    var left = document.createElement('div');
    left.className = 'metadata-assistant-review__source';
    var leftLabel = document.createElement('small');
    leftLabel.textContent = options.originalLabel;
    var leftText = document.createElement('span');
    leftText.textContent = options.originalText || t('compare_empty');
    left.appendChild(leftLabel);
    left.appendChild(leftText);
    var right = document.createElement('div');
    right.className = 'metadata-assistant-review__suggestion-value';
    var rightLabel = document.createElement('small');
    rightLabel.textContent = options.proposalLabel;
    right.appendChild(rightLabel);
    var box = null, cm = null, editor = null;
    if (options.editable) {
      var original = String(options.originalText || '');
      var showChanges = !!(options.diff && original.trim());
      box = document.createElement('textarea');
      box.className = 'form-control metadata-assistant-review__edit';
      box.rows = Math.max(2, Math.ceil(String(options.proposalText || '').length / 40));
      box.value = options.proposalText;
      box.setAttribute('data-original', options.proposalText);
      box.setAttribute('aria-label', (options.fieldLabel ? options.fieldLabel + ': ' : '') + options.proposalLabel);

      var editPane = document.createElement('div');
      editPane.appendChild(box);
      // With CodeMirror the changes are marked in the text itself; without it the box stays a plain text box
      // and the changes are listed below it. `editor` is what the toolbar, the "keep the original" edits and the
      // preview talk to: the box, or the CodeMirror stand-in for it.
      editor = box;
      if (showChanges && typeof window !== 'undefined' && window.CodeMirror) {
        cm = window.CodeMirror.fromTextArea(box, { lineWrapping: true, viewportMargin: Infinity, styleSelectedText: true });
        cm.on('change', function () { cm.save(); });   // the box keeps the current text (hasPendingEdit reads it)
        editor = codeMirrorBox(cm);
      }
      if (options.markdown) editPane.insertBefore(buildMarkdownToolbar(editor), editPane.firstChild);

      var previewPane = document.createElement('div');
      previewPane.className = 'metadata-assistant-review__preview';
      previewPane.hidden = true;

      var changesPane = document.createElement('div');
      changesPane.className = 'metadata-assistant-review__changes';
      var showRemoved = true;
      var marks = [];
      var contextSpan = function (value) {
        var span = document.createElement('span');
        span.className = 'metadata-assistant-review__context';
        span.textContent = value;
        return span;
      };
      // In the text: the added words marked, and at each change a small piece that shows what was removed (when
      // the tick box says so) with a button to keep the original there. The pieces are not part of the text.
      var markInText = function (changes) {
        cm.operation(function () {
          marks.forEach(function (mark) { mark.clear(); });
          marks = [];
          changes.forEach(function (change) {
            var from = cm.posFromIndex(change.start);
            var to = cm.posFromIndex(change.start + change.added.length);
            if (change.added) marks.push(cm.markText(from, to, { className: 'metadata-assistant-review__add-mark' }));
            var piece = document.createElement('span');
            piece.className = 'metadata-assistant-review__piece';
            if (showRemoved && change.removed) {
              var gone = document.createElement('del');
              gone.className = 'metadata-assistant-review__del';
              gone.textContent = change.removed;
              piece.appendChild(gone);
            }
            var restore = document.createElement('button');
            restore.type = 'button';
            restore.className = 'metadata-assistant-review__restore';
            restore.textContent = '↺';
            restore.title = t('keep_original') + (change.removed ? ': ' + change.removed.slice(0, 80) : '');
            restore.setAttribute('aria-label', t('keep_original'));
            restore.addEventListener('mousedown', function (event) { event.preventDefault(); });
            restore.addEventListener('click', function () { revertChange(editor, change); });
            piece.appendChild(restore);
            marks.push(cm.setBookmark(from, { widget: piece, insertLeft: true }));
          });
        });
      };
      var renderChanges = function () {
        changesPane.textContent = '';
        if (!showChanges) return;
        // Marked in the text, changes can be fine (only ones one word apart are joined); as a list they are joined more.
        var changes = diffChanges(original, editor.value, cm ? 1 : 3);
        var head = document.createElement('div');
        head.className = 'metadata-assistant-review__changes-head';
        var title = document.createElement('strong');
        title.textContent = changes.length ? t('changes_heading', { count: changes.length }) : t('diff_none');
        head.appendChild(title);
        if (changes.length) {
          var label = document.createElement('label');
          label.className = 'metadata-assistant-review__show-removed';
          var tick = document.createElement('input');
          tick.type = 'checkbox';
          tick.checked = showRemoved;
          tick.addEventListener('change', function () { showRemoved = tick.checked; renderChanges(); });
          label.appendChild(tick);
          label.appendChild(document.createTextNode(' ' + t('show_removed')));
          head.appendChild(label);
        }
        changesPane.appendChild(head);
        if (cm) markInText(changes);
        if (!cm) {
          var list = document.createElement('ol');
          list.className = 'metadata-assistant-review__change-list';
          changes.forEach(function (change) {
            var item = document.createElement('li');
            var text = document.createElement('div');
            text.className = 'metadata-assistant-review__change';
            if (change.before) text.appendChild(contextSpan('… ' + change.before.replace(/^\s+/, '')));
            if (showRemoved && change.removed) {
              var gone = document.createElement('del');
              gone.className = 'metadata-assistant-review__del';
              gone.textContent = visibleRemoved(change.removed);
              text.appendChild(gone);
            }
            if (change.added) {
              var plus = document.createElement('ins');
              plus.className = 'metadata-assistant-review__add';
              plus.textContent = change.added;
              text.appendChild(plus);
            }
            if (change.after) text.appendChild(contextSpan(change.after.replace(/\s+$/, '') + ' …'));
            var keep = document.createElement('button');
            keep.type = 'button';
            keep.className = 'btn btn-outline-secondary btn-sm metadata-assistant-review__keep';
            keep.textContent = t('keep_original');
            keep.addEventListener('click', function () { revertChange(editor, change); });
            item.appendChild(text);
            item.appendChild(keep);
            list.appendChild(item);
          });
          changesPane.appendChild(list);
        }
        if (editor.value !== options.proposalText) {
          var again = document.createElement('button');
          again.type = 'button';
          again.className = 'btn btn-link btn-sm';
          again.textContent = t('use_whole');
          again.addEventListener('click', function () { mdEdit(editor, 0, editor.value.length, options.proposalText, 0, 0); });
          changesPane.appendChild(again);
        }
      };
      var timer = null;
      var changed = function () {
        if (timer) clearTimeout(timer);
        timer = setTimeout(renderChanges, 150);
      };
      if (cm) cm.on('change', changed); else box.addEventListener('input', changed);

      var modes = options.markdown ? ['edit', 'preview'] : ['edit'];
      var labels = { edit: t('diff_edit'), preview: t('diff_preview') };
      var buttons = {};
      var show = function (mode) {
        Object.keys(buttons).forEach(function (name) { buttons[name].setAttribute('aria-pressed', name === mode ? 'true' : 'false'); });
        editPane.hidden = mode !== 'edit';
        changesPane.hidden = mode !== 'edit';
        previewPane.hidden = mode !== 'preview';
        if (mode === 'edit') { if (cm) cm.refresh(); else autosize(box); renderChanges(); }
        if (mode === 'preview') renderPreview(editor.value, previewPane);
      };
      if (modes.length > 1) {
        var tabs = document.createElement('div');
        tabs.className = 'metadata-assistant-review__tabs';
        tabs.setAttribute('role', 'group');
        modes.forEach(function (mode) {
          var button = document.createElement('button');
          button.type = 'button';
          button.className = 'btn btn-outline-secondary btn-sm metadata-assistant-review__tab';
          button.textContent = labels[mode];
          button.setAttribute('aria-pressed', 'false');
          button.addEventListener('click', function () { show(mode); });
          buttons[mode] = button;
          tabs.appendChild(button);
        });
        right.appendChild(tabs);
      }
      right.appendChild(editPane);
      right.appendChild(changesPane);
      right.appendChild(previewPane);
      show('edit');
    } else {
      var shown = document.createElement('span');
      shown.textContent = options.proposalText;
      right.appendChild(shown);
      var note = document.createElement('small');
      note.textContent = t('compare_choice_note');
      right.appendChild(note);
    }
    wrap.appendChild(left);
    wrap.appendChild(right);
    if (box && !cm) {
      autosizeOnInput(box);
      // Measured again once the box is on the page (and when its <details> is opened): not before.
      setTimeout(function () { autosize(box); }, 0);
    }
    // CodeMirror measures the page too, so it is told once the box is on it.
    if (cm) setTimeout(function () { cm.refresh(); }, 0);
    return { element: wrap, original: left, proposal: right, value: function () { return box ? editor.value : null; } };
  }

  function dispatchFieldChange(field) {
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // The field a suggestion updates usually lives far away from the review
  // panel in the form (title, notes, tags... are scattered through the
  // normal CKAN layout). Moving keyboard focus there would scroll the
  // editor away from the panel and out of view of any other suggestions
  // still waiting to be reviewed. Instead, briefly flash the field itself
  // so there is still a clear visual confirmation without losing your
  // place in the suggestions list.
  function visibleElementFor(field) {
    if (typeof window !== 'undefined' && window.jQuery) {
      var select2Container = window.jQuery(field).data('select2') && window.jQuery(field).next('.select2-container');
      if (select2Container && select2Container.length) return select2Container[0];
    }
    return field;
  }

  function flashField(field) {
    var target = visibleElementFor(field);
    var flashClass = 'metadata-assistant-review__field-flash';
    target.classList.remove(flashClass);
    // Force a reflow so the animation restarts if the same field is
    // flashed again before the previous flash finished.
    void target.offsetWidth;
    target.classList.add(flashClass);
    var clear = function () { target.classList.remove(flashClass); };
    target.addEventListener('animationend', clear, { once: true });
    // Fallback in case the animationend event doesn't fire (e.g. reduced
    // motion settings suppress the animation).
    setTimeout(clear, 2000);
  }

  // A suggestion written into the form changes a field without the editor leaving it: tell the panel, so that the rule
  // check runs again and a finding the suggestion has dealt with goes away.
  function announceApplied(form) {
    if (!form || typeof form.dispatchEvent !== 'function' || typeof Event !== 'function') return;
    form.dispatchEvent(new Event('metadata-assistant:applied'));
  }

  function applySuggestion(form, suggestion) {
    var field = fieldControl(form, suggestion.field);
    if (!field) return false;

    if (suggestion.field === 'tag_string') {
      // Keywords are ADDED to the ones already there, never replacing them
      // (2026-09-27: applying a suggestion wiped the existing keywords
      // and kept only the first suggested one). The old code called
      // select2('val', ...), a select2 v3 API; CKAN 2.12 runs select2 v4,
      // where the tag field is a plain <input> whose selection CKAN's data
      // adapter reads back from the input's comma-separated value
      // (formatInitialValue). So: write the merged list to the input and let
      // the change event make select2 re-render from it.
      var split = function (value) {
        return String(value || '').split(',').map(function (item) { return item.trim(); }).filter(Boolean);
      };
      var suggested = Array.isArray(suggestion.suggested_value) ?
        suggestion.suggested_value.map(function (item) { return String(item).trim(); }).filter(Boolean) :
        split(suggestion.suggested_value);
      var seen = {};
      var merged = [];
      split(field.value).concat(suggested).forEach(function (keyword) {
        var key = keyword.toLowerCase();
        if (!seen[key]) {
          seen[key] = true;
          merged.push(keyword);
        }
      });
      field.value = merged.join(', ');
      dispatchFieldChange(field);
      flashField(field);
      return true;
    }

    if (suggestion.field === 'theme' && field.options) {
      var themes = Array.isArray(suggestion.suggested_value) ? suggestion.suggested_value : [suggestion.suggested_value];
      Array.prototype.forEach.call(field.options, function (option) {
        option.selected = themes.indexOf(option.value) !== -1;
      });
      dispatchFieldChange(field);
      flashField(field);
      return true;
    }

    field.value = suggestionText(suggestion.suggested_value);
    dispatchFieldChange(field);
    flashField(field);
    return true;
  }



  // 2026-09-23: landing_page_used is set by the provider, never by the model.
  // Only an explicit false means "we tried to read the page and could not".
  // undefined/null mean the question does not apply -- no page was supplied,
  // or the provider has no managed fetch at all -- and must stay silent, or
  // every review would carry a warning about something that never happened.
  function shouldWarnAboutLandingPage(result) {
    return result && result.landing_page_used === false;
  }

  // 2026-09-27: "Suggest English"; 2026-10-01 any language. The input for
  // a suggestion is named after its target field and language, e.g.
  // "title_translated-en" or "keywords_translated-en" (ckanext-fluent).
  // Keywords are added to what is already there; texts replace the box.
  function translationControl(form, suggestion) {
    return form.querySelector('[name="' + suggestion.target_field + '-' + suggestion.language + '"]');
  }

  function applyTranslation(form, suggestion) {
    var field = translationControl(form, suggestion);
    if (!field) return false;
    if (Array.isArray(suggestion.suggested_value)) {
      var seen = {};
      var merged = [];
      String(field.value || '').split(',').map(function (v) { return v.trim(); }).filter(Boolean)
        .concat(suggestion.suggested_value.map(function (v) { return String(v).trim(); }).filter(Boolean))
        .forEach(function (keyword) {
          var key = keyword.toLowerCase();
          if (!seen[key]) { seen[key] = true; merged.push(keyword); }
        });
      field.value = merged.join(', ');
    } else {
      field.value = String(suggestion.suggested_value || '');
    }
    dispatchFieldChange(field);
    flashField(field);
    return true;
  }

  // The form has an input for at least one of the target languages.
  function hasTranslationTargets(form, languages) {
    return (languages || []).some(function (language) {
      return !!form.querySelector('[name$="-' + language + '"]');
    });
  }

  function capitalize(text) {
    text = String(text || '');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function renderTranslations(container, result, form, status) {
    container.textContent = '';
    container.hidden = false;
    var heading = document.createElement('h3');
    heading.textContent = t('translation_heading');
    container.appendChild(heading);
    var note = document.createElement('p');
    note.className = 'metadata-assistant-review__notice';
    note.textContent = t('translation_note');
    container.appendChild(note);

    orderLikeTheForm(form, result.suggestions || []).forEach(function (suggestion) {
      var item = document.createElement('div');
      item.className = 'metadata-assistant-review__suggestion';
      var label = document.createElement('strong');
      label.textContent = suggestion.label || fieldLabel(suggestion.field);
      // 2026-09-30: the original is shown next to the suggestion, so that the editor can judge
      // the translation. It is the source text that was actually translated (from the server), not
      // the field's current value. The suggestion can be edited before it is used.
      var compare = buildCompare({
        fieldLabel: suggestion.label || fieldLabel(suggestion.field),
        originalLabel: t('translation_source', {
          language: capitalize(suggestion.source_language_label || suggestion.source_language) }),
        originalText: suggestionText(suggestion.source_value),
        proposalLabel: t('translation_value', { language: suggestion.language_label || suggestion.language }),
        proposalText: suggestionText(suggestion.suggested_value),
        editable: true,
        diff: false,
        markdown: markdownEnabled && suggestion.field === 'notes'
      });
      var source = compare.original;
      var value = compare.proposal;
      var apply = document.createElement('button');
      apply.type = 'button';
      apply.className = 'btn btn-primary metadata-assistant-review__apply';
      setApplyLabel(apply);
      apply.addEventListener('click', function () {
        var edited = withEditedValue(suggestion, compare.value());
        if (isBlankSuggestion(edited)) {
          status.textContent = t('compare_blank');
          return;
        }
        if (applyTranslation(form, edited)) {
          announceApplied(form);
          apply.disabled = true;
          apply.textContent = t('suggestion_used');
          item.classList.add('metadata-assistant-review__suggestion--applied');
          label.textContent = '\u2713 ' + t('translation_applied_label', {
            field: label.textContent, language: suggestion.language_label || suggestion.language });
          value.hidden = true;
          source.hidden = true;
          compare.element.hidden = true;
          status.textContent = t('translation_applied');
          showToast(t('toast_not_saved'));
        } else {
          status.textContent = t('translation_field_missing');
        }
      });
      item.appendChild(label);
      item.appendChild(compare.element);
      item.appendChild(apply);
      container.appendChild(item);
    });

    (result.failed || []).forEach(function (failure) {
      var notice = document.createElement('p');
      notice.className = 'metadata-assistant-review__notice';
      notice.textContent = t('translation_language_failed', {
        language: failure.language_label || failure.language, error: failure.error });
      container.appendChild(notice);
    });
  }

  // 2026-09-30: the AI suggestions are at the bottom of the panel, but the
  // automatic check runs when one leaves a field higher up. A fixed button
  // says there are suggestions to review and takes one there. It hides when
  // the panel is in view, comes back when one scrolls away from it, and
  // disappears only when all suggestions have been used (2026-10-01).
  function pendingSuggestionsText(count) {
    return t('pending_suggestions', { count: count });
  }

  // A short notice that fades after a few seconds, for what the page does that the editor might take for "saved" (2026-10-29: a used
  // suggestion is only in the form until the dataset is saved). One notice at a time; a click closes it.
  var toastTimer = null;
  function showToast(message, doc, seconds) {
    doc = doc || document;
    var toast = doc.querySelector('.metadata-assistant-review__toast');
    if (!toast) {
      toast = doc.createElement('div');
      toast.className = 'metadata-assistant-review__toast';
      toast.setAttribute('role', 'status');
      toast.addEventListener('click', function () { toast.hidden = true; });
      doc.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.hidden = true; }, (seconds || 6) * 1000);
    return toast;
  }

  // The parts of a text that are web addresses: [{text, href}] (href is empty for plain text). Trailing punctuation is not part of the address.
  function linkParts(text) {
    var parts = [];
    var pattern = /https?:\/\/[^\s<>"]+/g;
    var last = 0;
    var match;
    text = String(text || '');
    while ((match = pattern.exec(text)) !== null) {
      var url = match[0].replace(/[.,;:!?)]+$/, '');
      if (match.index > last) parts.push({ text: text.slice(last, match.index), href: '' });
      parts.push({ text: url, href: url });
      last = match.index + url.length;
      pattern.lastIndex = last;
    }
    if (last < text.length) parts.push({ text: text.slice(last), href: '' });
    return parts;
  }

  // Text with its web addresses as links (built from nodes, never as HTML), opened in a new tab.
  function appendLinked(element, text) {
    linkParts(text).forEach(function (part) {
      if (!part.href) {
        element.appendChild(document.createTextNode(part.text));
        return;
      }
      var link = document.createElement('a');
      link.href = part.href;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = part.text;
      element.appendChild(link);
    });
  }

  // The button that puts a suggestion into the form: a full-size primary button with a tick, so it cannot be missed.
  function setApplyLabel(button) {
    button.textContent = '';
    var icon = document.createElement('i');
    icon.className = 'fa fa-check';
    icon.setAttribute('aria-hidden', 'true');
    button.appendChild(icon);
    button.appendChild(document.createTextNode(' ' + t('use_suggestion')));
  }

  // Suggestions that are shown but not used yet: their buttons are still enabled. `root` is the document (the panel's results are moved
  // to a box in the page footer, so the panel itself does not hold them).
  function unusedSuggestionButtons(root) {
    return Array.prototype.filter.call(root.querySelectorAll('.metadata-assistant-review__apply'), function (button) { return !button.disabled; });
  }

  // "Update dataset" with suggestions left unused asks what to do with them: use them (and save), discard them (and save) or go back
  // (2026-10-29: a suggestion that was not used was silently lost when the page was saved).
  function guardUnusedSuggestions(form) {
    if (typeof HTMLDialogElement === 'undefined' || !form.addEventListener) return;
    var asked = false;
    form.addEventListener('submit', function (event) {
      var pending = asked ? [] : unusedSuggestionButtons(document);
      if (!pending.length) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      var submitter = event.submitter;
      var dialog = document.createElement('dialog');
      dialog.className = 'metadata-assistant-review__unused';
      var text = document.createElement('p');
      text.textContent = t('unused_message');
      dialog.appendChild(text);
      var buttons = document.createElement('div');
      buttons.className = 'metadata-assistant-review__unused-buttons';
      dialog.appendChild(buttons);
      function choice(label, className, action) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn ' + className;
        button.textContent = label;
        button.addEventListener('click', function () {
          dialog.close();
          dialog.remove();
          if (action) action();
        });
        buttons.appendChild(button);
      }
      function save() {
        asked = true;
        if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit();
      }
      choice(t('unused_save'), 'btn-primary', function () {
        pending.forEach(function (button) { button.click(); });
        save();
      });
      choice(t('unused_discard'), 'btn-outline-secondary', save);
      choice(t('unused_back'), 'btn-link', null);
      document.body.appendChild(dialog);
      try {
        dialog.showModal();
      } catch (error) {
        // A dialog that cannot be shown must never leave the form unsendable: send it as it is.
        dialog.remove();
        setTimeout(save, 0);   // a nested requestSubmit during the submit event itself does nothing
      }
    }, true);
  }

  function buildSuggestionNotice(target, statusLine) {
    var notice = document.createElement('button');
    notice.type = 'button';
    notice.className = 'metadata-assistant-review__new-suggestions';
    notice.hidden = true;
    notice.setAttribute('aria-live', 'polite');
    document.body.appendChild(notice);

    var pending = 0;
    var busy = '';   // what the AI is doing right now (2026-10-01)
    var visible = false;

    function render() {
      notice.hidden = !(pending || busy) || visible;
      if (notice.hidden) return;
      notice.innerHTML = '';
      var icon = document.createElement('i');
      icon.className = busy ? 'fa fa-spinner fa-spin' : 'fa fa-lightbulb-o';
      icon.setAttribute('aria-hidden', 'true');
      notice.appendChild(icon);
      notice.appendChild(document.createTextNode(' ' + (busy || pendingSuggestionsText(pending)) + ' '));
      var arrow = document.createElement('i');
      arrow.className = 'fa fa-arrow-down';
      arrow.setAttribute('aria-hidden', 'true');
      notice.appendChild(arrow);
    }

    notice.addEventListener('click', function () {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    if (typeof IntersectionObserver !== 'undefined') {
      new IntersectionObserver(function (entries) {
        visible = entries.some(function (entry) { return entry.isIntersecting; });
        render();
      }).observe(target);
    }

    return {
      setPending: function (count) { pending = count || 0; render(); },
      // The panel's own status line shows the same, since the button hides
      // when the panel is in view (2026-10-01: "does the AI stop working
      // when I scroll to the bottom?").
      setBusy: function (text) {
        busy = text || '';
        if (statusLine) statusLine.classList.toggle('is-busy', !!busy);
        render();
      },
      used: function () { pending = Math.max(0, pending - 1); render(); }
    };
  }

  function renderAIResults(container, result, form, status, onUsed) {
    container.textContent = '';
    container.hidden = false;

    var heading = document.createElement('h3');
    heading.textContent = t('ai_heading');
    container.appendChild(heading);

    var summary = document.createElement('p');
    summary.textContent = result.summary;
    container.appendChild(summary);

    if (shouldWarnAboutLandingPage(result)) {
      var notice = document.createElement('p');
      notice.className = 'metadata-assistant-review__notice';
      notice.textContent = t('landing_page_notice');
      container.appendChild(notice);
    }

    var remaining = (result.suggestions || []).filter(function (suggestion) {
      return newKeywordsOnly(currentFieldText(form, suggestion.field), suggestion);
    });
    if (!remaining.length && !(result.questions_for_editor || []).length) {
      var nothing = document.createElement('p');
      nothing.className = 'metadata-assistant-review__notice';
      nothing.textContent = t('ai_nothing');
      container.appendChild(nothing);
    }

    orderLikeTheForm(form, result.suggestions || []).map(function (suggestion) {
      return newKeywordsOnly(currentFieldText(form, suggestion.field), suggestion);
    }).filter(Boolean).forEach(function (suggestion) {
      var item = document.createElement('div');
      item.className = 'metadata-assistant-review__suggestion';
      var label = document.createElement('strong');
      label.textContent = fieldLabel(suggestion.field);
      var choice = suggestion.field === 'theme' && form && fieldControl(form, 'theme') &&
        fieldControl(form, 'theme').options;
      var compare = buildCompare({
        fieldLabel: fieldLabel(suggestion.field),
        originalLabel: t('compare_current'),
        originalText: currentFieldText(form, suggestion.field),
        proposalLabel: suggestion.field === 'tag_string' ? t('compare_proposal_add') : t('compare_proposal'),
        proposalText: choice ? suggestionDisplayText(form, suggestion) : suggestionText(suggestion.suggested_value),
        editable: !choice,
        diff: suggestion.field === 'notes',   // a title is short: the box alone is enough
        markdown: markdownEnabled && suggestion.field === 'notes'
      });
      var value = compare.element;
      var reason = document.createElement('small');
      reason.className = 'help-block';
      reason.textContent = suggestion.reason;
      var apply = document.createElement('button');
      apply.type = 'button';
      apply.className = 'btn btn-primary metadata-assistant-review__apply';
      setApplyLabel(apply);
      apply.addEventListener('click', function () {
        var edited = compare.value() === null ? suggestion : withEditedValue(suggestion, compare.value());
        if (isBlankSuggestion(edited)) {
          status.textContent = t('compare_blank');
          return;
        }
        if (applySuggestion(form, edited)) {
          announceApplied(form);
          if (onUsed) onUsed();
          apply.disabled = true;
          apply.textContent = t('suggestion_used');
          item.classList.add('metadata-assistant-review__suggestion--applied');
          // 2026-09-09: collapse the used suggestion to one line --
          // more applied suggestions should not make the box taller
          // and hide more of the form than needed.
          label.textContent = '\u2713 ' + fieldLabel(suggestion.field);
          value.hidden = true;
          reason.hidden = true;
          status.textContent = t('suggestion_applied', { field: fieldLabel(suggestion.field).toLowerCase() });
          showToast(t('toast_not_saved'));
        } else {
          status.textContent = t('suggestion_field_missing');
        }
      });
      item.appendChild(label);
      item.appendChild(value);
      item.appendChild(reason);
      item.appendChild(apply);
      container.appendChild(item);
    });

    if ((result.questions_for_editor || []).length) {
      var questionHeading = document.createElement('strong');
      questionHeading.textContent = t('questions_heading');
      container.appendChild(questionHeading);
      var questions = document.createElement('ul');
      questions.className = 'metadata-assistant-review__questions';
      result.questions_for_editor.forEach(function (question) {
        var item = document.createElement('li');
        item.textContent = question;
        questions.appendChild(item);
      });
      container.appendChild(questions);
    }
  }

  function draftForPanel(form, panel) {
    var draft = formDraft(form);
    if (panel.dataset.datasetId) draft.id = panel.dataset.datasetId;
    return draft;
  }

  function requestHeaders(form) {
    var headers = { 'Content-Type': 'application/json' };
    var csrf = form && form.querySelector('input[name="_csrf_token"]');
    if (csrf && csrf.value) headers['X-CSRFToken'] = csrf.value;
    return headers;
  }

  // The panel's template gives the API address with the page's language (/en/api/3/action/ on an English page), so the
  // server answers in that language; without it, CKAN's default language would answer.
  var apiBase = '/api/3/action/';

  function postReview(action, draft, form, extras) {
    var payload = { dataset: draft };
    if (extras) {
      Object.keys(extras).forEach(function (key) { payload[key] = extras[key]; });
    }
    return fetch(apiBase + action, {
      method: 'POST', credentials: 'same-origin',
      headers: requestHeaders(form),
      body: JSON.stringify(payload)
    }).then(function (response) { return response.json(); });
  }

  function postAction(action, body, form) {
    return fetch(apiBase + action, {
      method: 'POST', credentials: 'same-origin',
      headers: requestHeaders(form),
      body: JSON.stringify(body)
    }).then(function (response) { return response.json(); });
  }

  // The AI requests run as background jobs (see jobs.py): start one, then ask how it is going until it is
  // done. The outcome has the shape of a CKAN API answer, so the callers need not know about jobs.
  var JOB_LIMIT_MS = 6 * 60 * 1000;

  function jobOutcome(job) {
    if (job.state === 'done') {
      return { success: true, result: job.result, cached: !!job.cached, prepared_at: job.prepared_at || null };
    }
    if (job.state === 'none') return { success: true, none: true };
    return { success: false, error: { ai: [job.error || t('ai_failed')] } };
  }

  function followJob(job, form, onProgress, startedAt, lost, delay) {
    if (job.state === 'done' || job.state === 'failed' || job.state === 'none') {
      return Promise.resolve(jobOutcome(job));
    }
    if (onProgress) onProgress(job);
    if (Date.now() - startedAt > JOB_LIMIT_MS) {
      return Promise.resolve({ success: false, error: { ai: [t('job_timeout')] } });
    }
    return new Promise(function (resolve) { setTimeout(resolve, delay); }).then(function () {
      return postAction('metadata_assistant_job_status', { job_id: job.job_id || job.id }, form)
        .then(function (payload) {
          if (!payload.success) return { fatal: payload.error };   // the job is gone, or not yours
          return { job: Object.assign({ job_id: job.job_id || job.id }, payload.result) };
        })
        .catch(function () { return { lost: true }; });   // the network, not the job
    }).then(function (next) {
      if (next.job) return followJob(next.job, form, onProgress, startedAt, 0, Math.min(delay + 500, 3000));
      if (next.fatal) {
        var why = firstErrorMessage(next.fatal) || (next.fatal && next.fatal.message) || '';
        return { success: false, error: { ai: [why || t('job_lost')] } };
      }
      if (lost >= 2) return { success: false, error: { ai: [t('job_lost')] } };
      return followJob(job, form, onProgress, startedAt, lost + 1, delay);
    });
  }

  function postJob(kind, body, form, onProgress) {
    var payload = Object.assign({ kind: kind }, body);
    return postAction('metadata_assistant_job_start', payload, form).then(function (started) {
      if (!started.success) return started;
      return followJob(Object.assign({ job_id: started.result.job_id }, started.result), form, onProgress,
                       Date.now(), 0, 1000);
    });
  }

  // How old the downloaded copy of the landing page is, as "2 hours ago" in the page's language.
  function ageText(fetchedAt, now) {
    var then = new Date(fetchedAt);
    if (isNaN(then)) return '';
    var seconds = Math.max(0, Math.round(((now || new Date()) - then) / 1000));
    var units = [['day', 86400], ['hour', 3600], ['minute', 60]];
    var unit = 'minute', value = 0;
    for (var i = 0; i < units.length; i++) {
      if (seconds >= units[i][1]) { unit = units[i][0]; value = Math.floor(seconds / units[i][1]); break; }
    }
    if (typeof Intl !== 'undefined' && Intl.RelativeTimeFormat) {
      return new Intl.RelativeTimeFormat(pageLanguage(), { numeric: 'auto' }).format(-value, unit);
    }
    return value + ' ' + unit;
  }

  function pageLanguage() {
    var lang = typeof document !== 'undefined' && document.documentElement && document.documentElement.lang;
    return lang ? [lang] : [];
  }

  function progressText(running) {
    return function (job) {
      if (job.state === 'queued') {
        return t(job.position ? 'job_queued_position' : 'job_queued', { count: job.position || 0 });
      }
      return running;
    };
  }

  var AI_TRACKED_FIELDS = ['title', 'notes', 'tag_string', 'theme', 'language', 'url'];

  // 2026-09-23: the snapshot carries which landing page reading the review
  // was based on. The landing page read is slow (40-90s), so the editor can
  // easily have triggered a review BEFORE it lands. Making the extract part
  // of the snapshot means the review is re-run automatically when it arrives
  // -- the freshness rule enforces it, rather than a caller remembering to.
  function aiTrackedSnapshot(form, extractKey) {
    var draft = formDraft(form);
    var snapshot = {};
    AI_TRACKED_FIELDS.forEach(function (key) {
      snapshot[key] = draft[key] !== undefined ? draft[key] : '';
    });
    snapshot.__extract = extractKey || '';
    return snapshot;
  }

  function snapshotsEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
  }

  // Identifies which landing-page reading a review was based on.
  // '' = no reading yet (a review now would be provisional), the URL = the
  // page was read, 'none' = we tried and gave up. The last two differ from
  // '', which is what makes a review taken mid-read count as stale.
  function landingPageExtractKey(state) {
    if (!state) return '';
    if (state.extract) return state.url || '';
    if (state.status === 'failed') return 'none';
    return '';
  }

  // Whether leaving a field should start an automatic review: only when something the AI looks at differs from
  // what the last review saw, or, before any review, from what the page held when it was opened. Leaving a field
  // without changing anything does nothing.
  function autoCheckNeeded(snapshot, last, baseline) {
    if (!snapshotHasContent(snapshot)) return false;
    var reference = last || baseline;
    return !(reference && snapshotsEqual(snapshot, reference));
  }

  function snapshotHasContent(snapshot) {
    // __extract is bookkeeping, not editor input -- ignore it here.
    return AI_TRACKED_FIELDS.some(function (key) {
      var value = snapshot[key];
      if (Array.isArray(value)) return value.length > 0;
      return !!(value && String(value).trim());
    });
  }

  // Sets up one review panel. The AI suggestions are shown in the panel itself;
  // since the check can also start automatically when one leaves a field (see
  // AI_TRACKED_FIELDS/runAiCheck below), a floating button points to new ones.
  function initialize(panel) {
    var form = panel.closest('form');
    try { setStrings(JSON.parse(panel.getAttribute('data-i18n') || '{}')); } catch (e) { /* English */ }
    apiBase = panel.getAttribute('data-api-base') || apiBase;
    var aiButton = panel.querySelector('[data-metadata-assistant-ai-start]');
    var status = panel.querySelector('[data-metadata-assistant-status]');
    var results = panel.querySelector('[data-metadata-assistant-results]');
    var aiStatus = panel.querySelector('[data-metadata-assistant-ai-status]');
    activeForm = form;
    guardUnusedSuggestions(form);
    markdownEnabled = panel.getAttribute('data-markdown') === 'true';
    var stackHost = panel.querySelector('[data-metadata-assistant-stack]');
    if (!form || !aiButton || !status || !results || !aiStatus || !stackHost) return;
    var actionsRow = panel.querySelector('.metadata-assistant-review__actions');
    // Keep the buttons in view when a box is brought to the editor's attention.
    // The description boxes of the form itself grow with their text too (also when a suggestion is used).
    Array.prototype.forEach.call(form.querySelectorAll('textarea[name="notes"], textarea[name^="notes_translated-"]'), function (area) {
      autosizeOnInput(area);
      if (markdownEnabled && area.parentNode) area.parentNode.insertBefore(buildMarkdownToolbar(area), area);
    });
    var stack = createResultStack(stackHost, function (element) {
      if (!actionsRow || typeof window === 'undefined') { element.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); return; }
      var delta = scrollDeltaToReveal(actionsRow.getBoundingClientRect().top,
                                      element.getBoundingClientRect().top, window.innerHeight);
      if (delta) window.scrollBy({ top: delta, behavior: 'smooth' });
    });
    // 2026-09-30: the AI suggestions are shown in the panel (aiStatus/aiResults),
    // no longer in the fixed footer box introduced 2026-09-09.
    var suggestionNotice = buildSuggestionNotice(stackHost, aiStatus);

    function sameAsLastRun(set) {
      return set && isUntouched(set) && set.snapshot && snapshotsEqual(aiTrackedSnapshot(form, extractKey()), set.snapshot);
    }

    var translateButton = panel.querySelector('[data-metadata-assistant-translate-start]');
    var translateStatus = panel.querySelector('[data-metadata-assistant-translate-status]');
    if (translateButton && translateStatus) {
      var languages = [];
      try { languages = JSON.parse(panel.getAttribute('data-translation-languages') || '[]'); } catch (e) { languages = []; }
      if (!hasTranslationTargets(form, languages)) {
        translateButton.hidden = true;
      } else {
        var runTranslate = function () {
          var currentTranslation = stack.latest('translation');
          if (currentTranslation && hasPendingEdit(currentTranslation.body) && typeof window !== 'undefined' &&
              typeof window.confirm === 'function' && !window.confirm(t('replace_edited'))) return;
          translateButton.disabled = true;
          translateStatus.textContent = t('translation_running');
          translateStatus.classList.add('is-busy');
          suggestionNotice.setBusy(t('translation_running'));
          var snapshot = aiTrackedSnapshot(form, extractKey());
          postJob('translate', { dataset: draftForPanel(form, panel) }, form, function (job) {
            translateStatus.textContent = progressText(t('translation_running'))(job);
          })
            .then(function (payload) {
              if (!payload.success) {
                throw new Error(firstErrorMessage(payload.error) || t('translation_failed'));
              }
              var suggestions = payload.result.suggestions || [];
              translateStatus.textContent = suggestions.length ?
                t('translation_done') : t('translation_nothing');
              var set = stack.add('translation', t('set_translation'));
              set.snapshot = snapshot;
              renderTranslations(set.body, payload.result, form, translateStatus);
              if (set.replaced) {
                translateStatus.textContent = t('set_replaced', { time: set.time, old: set.previousTime });
                flashSet(set.element);
              }
              stack.reveal(set.element);
            })
            .catch(function (error) {
              translateStatus.textContent = (error && error.message) ||
                t('translation_failed_retry');
            })
            .finally(function () {
              translateButton.disabled = false;
              translateStatus.classList.remove('is-busy');
              suggestionNotice.setBusy('');
            });
        };
        translateButton.addEventListener('click', function () {
          var latestSet = stack.latest('translation');
          if (sameAsLastRun(latestSet)) { stack.present(latestSet, runTranslate); return; }
          runTranslate();
        });
      }
    }
    // The completeness check (rules, no AI, free) runs by itself: when the page opens and after a field has been
    // left with something changed. Its summary is one line; the findings open under it.
    var rulesTimer = null, rulesDraft = null;
    // 2026-10-17: an address the editor has just typed or changed is checked by the link check (if the sysadmin has turned that
    // on). The addresses the page opened with are not: the nightly check covers them. The answers are kept for as long as the
    // address stays in the form.
    var checkedAddresses = null, addressFindings = {}, rulesSeq = 0, lastPlainFindings = [];
    function linkAddresses() {
      var found = [];
      ['url', 'documentation', 'conforms_to'].forEach(function (name) {
        Array.prototype.forEach.call(form.querySelectorAll('[name="' + name + '"]'), function (field) {
          var value = (field.value || '').trim();
          if (/^https?:\/\//i.test(value) && found.indexOf(value) < 0) found.push(value);
        });
      });
      return found;
    }
    // 2026-10-18: a better address for what the editor has typed is offered right under the field, with a button that puts
    // it in the form (nothing is saved). The findings stay in the list as well.
    // Puts the better address in every address field that still holds the old one. Nothing is saved.
    function useAddress(finding) {
      var changed = false;
      ['url', 'documentation', 'conforms_to'].forEach(function (name) {
        Array.prototype.forEach.call(form.querySelectorAll('[name="' + name + '"]'), function (field) {
          if ((field.value || '').trim() !== finding.address) return;
          field.value = finding.suggestion;
          field.dispatchEvent(new Event('input', { bubbles: true }));
          field.dispatchEvent(new Event('change', { bubbles: true }));
          changed = true;
        });
      });
      if (changed) { scheduleRules(); syncLandingPage(); }   // the landing page follows a changed address
      return changed;
    }
    function addressHints(kept) {
      Array.prototype.forEach.call(form.querySelectorAll('[data-metadata-assistant-address-hint]'), function (box) {
        box.parentNode.removeChild(box);
      });
      var better = {};
      kept.forEach(function (finding) { if (finding.suggestion) better[finding.address] = finding; });
      ['url', 'documentation', 'conforms_to'].forEach(function (name) {
        Array.prototype.forEach.call(form.querySelectorAll('[name="' + name + '"]'), function (field) {
          var finding = better[(field.value || '').trim()];
          if (!finding) return;
          var box = document.createElement('div');
          box.className = 'metadata-assistant-address-hint';
          box.setAttribute('data-metadata-assistant-address-hint', '');
          box.setAttribute('role', 'status');
          var text = document.createElement('span');
          text.textContent = t(finding.code === 'link_use_https_now' ? 'address_hint_https' : 'address_hint_forwards')
            .replace('{address}', finding.suggestion) + ' ';
          var use = document.createElement('button');
          use.type = 'button';
          use.className = 'btn btn-primary metadata-assistant-address-hint__use';
          use.textContent = t('address_hint_use');
          use.addEventListener('click', function () {
            if (useAddress(finding)) box.textContent = t('address_hint_used');
          });
          var why = document.createElement('div');
          why.className = 'metadata-assistant-address-hint__why';
          why.textContent = t(finding.code === 'link_use_https_now' ? 'address_hint_why_https' : 'address_hint_why_forwards');
          var changes = addressChanges(finding.address, finding.suggestion);
          var what = document.createElement('div');
          what.className = 'metadata-assistant-address-hint__what';
          what.textContent = t('address_change_heading') + ' ' +
            changes.map(function (key) { return t('address_change_' + key); }).join(', ') + '.';
          box.appendChild(text);
          if (changes.length) box.appendChild(what);
          box.appendChild(use);
          box.appendChild(why);
          field.parentNode.insertBefore(box, field.nextSibling);
        });
      });
    }
    // What is shown: the rule findings of the latest run and the answers about the addresses that are still in the form.
    function showRules() {
      var kept = [];
      linkAddresses().forEach(function (address) { (addressFindings[address] || []).forEach(function (f) { kept.push(f); }); });
      addressHints(kept);
      var findings = lastPlainFindings.concat(kept);
      status.textContent = rulesSummary(findings);
      renderResults(results, findings, useAddress);
    }
    function runRules() {
      var draft = JSON.stringify(draftForPanel(form, panel));
      if (draft === rulesDraft) return;
      rulesDraft = draft;
      var seq = ++rulesSeq;
      var current = panel.dataset.checkAddresses === 'true' ? linkAddresses() : [];
      if (checkedAddresses === null) checkedAddresses = current.slice();
      var fresh = current.filter(function (address) { return checkedAddresses.indexOf(address) < 0; });
      // An address counts as asked about from the moment it is sent, so a quick second change does not send it again.
      fresh.forEach(function (address) { checkedAddresses.push(address); });
      postReview('metadata_assistant_review_dataset', draftForPanel(form, panel), form,
                 fresh.length ? { check_addresses: fresh } : null)
        .then(function (payload) {
          if (!payload.success) throw new Error(t('rules_failed'));
          var findings = payload.result.findings || [];
          fresh.forEach(function (address) { addressFindings[address] = []; });
          findings.forEach(function (finding) {
            if (finding.address) addressFindings[finding.address] = (addressFindings[finding.address] || []).concat([finding]);
          });
          // An answer that arrives after a newer run keeps its address findings but not its rule findings.
          if (seq === rulesSeq) lastPlainFindings = findings.filter(function (finding) { return !finding.address; });
          showRules();
        })
        .catch(function () {
          rulesDraft = null;
          fresh.forEach(function (address) {
            var at = checkedAddresses.indexOf(address);
            if (at >= 0) checkedAddresses.splice(at, 1);
          });
          status.textContent = t('rules_failed_contact');
        });
    }
    function scheduleRules() {
      if (rulesTimer) clearTimeout(rulesTimer);
      rulesTimer = setTimeout(runRules, 800);
    }
    status.textContent = t('rules_running');
    runRules();
    form.addEventListener('focusout', scheduleRules);
    form.addEventListener('metadata-assistant:applied', scheduleRules);
    if (typeof window !== 'undefined' && window.jQuery) window.jQuery(form).on('select2:close', scheduleRules);

    // 2026-09-09: run the AI check automatically when one leaves one of the
    // fields it reviews (not only on a button press), so suggestions are
    // ready by the time one reaches the end of the form. Debounced so quick
    // tabbing through several fields does not start one review per field,
    // and skips the run if none of the reviewed fields has actually
    // changed since the last run.
    var autoCheckTimer = null;
    var aiCheckInFlight = false;
    var aiCheckQueued = false;
    var lastAiSnapshot = null;
    var baselineSnapshot = aiTrackedSnapshot(form, '');   // what the page held when it was opened

    // --- Landing page: read once per URL, then reuse -------------------
    // The managed fetch is the expensive, failure-prone half of an AI review
    // (40-90s, and the provider's capacity is not always there). Reading it
    // once and carrying the result turns every later review into a fast,
    // reliable call -- and keeps the number of AI calls down, which is the
    // point.
    var landingPage = { url: '', status: 'idle', extract: null };
    var lastUrlSeen = null;   // the address as the page opened, then as last left

    function landingPageUrl() {
      var field = form.querySelector('[name="url"]');
      return field && field.value ? field.value.trim() : '';
    }
    lastUrlSeen = landingPageUrl();

    // Identifies which reading a review was based on: the URL when we have an
    // extract, 'none' when we knowingly gave up on one. Both differ from '',
    // so either outcome invalidates a review made before the read finished.
    function extractKey() { return landingPageExtractKey(landingPage); }

    var rereadButton = panel.querySelector('[data-metadata-assistant-reread]');
    if (rereadButton) rereadButton.hidden = true;   // offered once a page has been downloaded and its age is known
    // The flow, as the editor sees it: the landing page, the AI analysis, then reading the suggestions. Shown
    // from the first step on, not before anything has been asked for.
    var flowHost = panel.querySelector('[data-metadata-assistant-flow]');
    function flow(step, state, text) {
      var item = flowHost && flowHost.querySelector('[data-step="' + step + '"]');
      if (!item) return;
      item.className = 'metadata-assistant-review__flow-step metadata-assistant-review__flow-step--' + state;
      item.textContent = text || '';
      item.hidden = !text;
      flowHost.hidden = false;
    }
    function showLandingAge(fetchedAt) {
      var age = fetchedAt ? ageText(fetchedAt) : '';
      if (age) flow('landing', 'done', t('landing_age', { age: age }));
      if (rereadButton) rereadButton.hidden = !age;
    }

    // An address that starts with http:// is not read at all (the server only reads https): say so at once, with a button that
    // puts the https address in the form (the one the link check offered, else the same address over https) and reads the page.
    // Nothing is saved.
    // A notice right under the landing page field (as for a better address): why the page was not read, with a button for what can be done.
    function clearLandingNotice() {
      Array.prototype.forEach.call(form.querySelectorAll('[data-metadata-assistant-landing-notice]'), function (box) {
        box.parentNode.removeChild(box);
      });
    }
    function landingNotice(message, buttonText, onClick) {
      clearLandingNotice();
      var field = form.querySelector('[name="url"]');
      if (!field || !field.parentNode) return;
      var box = document.createElement('div');
      box.className = 'metadata-assistant-address-hint';
      box.setAttribute('data-metadata-assistant-landing-notice', '');
      box.setAttribute('role', 'status');
      var text = document.createElement('span');
      text.textContent = message + ' ';
      box.appendChild(text);
      if (buttonText) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-primary metadata-assistant-address-hint__use';
        button.textContent = buttonText;
        button.addEventListener('click', onClick);
        box.appendChild(button);
      }
      field.parentNode.insertBefore(box, field.nextSibling);
    }

    function showHttpsStep(url) {
      flow('landing', 'failed', t('flow_landing_needs_https'));
      function useHttps() {
        // Looked up when clicked: the link check may have answered since the step was shown.
        var offered = (addressFindings[url] || []).filter(function (f) { return f.suggestion; })[0];
        useAddress({ address: url, suggestion: offered ? offered.suggestion : url.replace(/^http:/i, 'https:') });
      }
      landingNotice(t('flow_landing_needs_https'), t('flow_landing_use_https'), useHttps);
      var step = flowHost && flowHost.querySelector('[data-step="landing"]');
      if (!step) return;
      var switchButton = document.createElement('button');
      switchButton.type = 'button';
      switchButton.className = 'btn btn-primary btn-sm';
      switchButton.textContent = t('flow_landing_use_https');
      switchButton.addEventListener('click', useHttps);
      step.appendChild(document.createTextNode(' '));
      step.appendChild(switchButton);
    }

    function readLandingPage(url, fresh, quiet) {
      if (/^http:\/\//i.test(url)) {
        landingPage = { url: url, status: 'failed', extract: null };
        showHttpsStep(url);
        if (rereadButton) rereadButton.hidden = true;
        runAiCheck(!fresh);   // the review goes on with the texts in the form
        return;
      }
      clearLandingNotice();
      landingPage = { url: url, status: 'reading', extract: null, quiet: !!quiet, reviewWanted: false };
      flow('landing', 'active', t('flow_landing_reading'));
      // A read made when the form opens is quiet: no status text, and no review afterwards unless the editor has asked for one meanwhile.
      if (!quiet) {
        aiStatus.textContent = t('reading_landing_page');
        suggestionNotice.setBusy(t('busy_landing_page'));
      }
      var handled = false;   // the read is dealt with in the first step below: nothing more to do afterwards
      postJob('landing', { url: url, fresh: !!fresh, ahead: !!quiet }, form, function (job) {
        aiStatus.textContent = progressText(t('reading_landing_page'))(job);
      })
        .then(function (payload) {
          if (landingPage.url !== url) return;   // editor moved on
          // Read ahead of time, and the server did not (it is busy with another, or this page failed a moment ago) or it failed: nothing was
          // asked for, so there is no failure to show. If the editor asked for suggestions meanwhile, the page is read now, the ordinary way.
          if (quiet && ((payload.success && payload.none) || (!payload.success && !landingPage.reviewWanted))) {
            var wanted = landingPage.reviewWanted;
            landingPage = { url: '', status: 'idle', extract: null };
            flow('landing', 'none', '');
            handled = true;
            if (wanted) readLandingPage(url, false, false);
            return;
          }
          if (payload.success) {
            landingPage.status = 'ready';
            landingPage.extract = payload.result.extract;
            showLandingAge(payload.result.fetched_at);
            if (quiet && snapshotsEqual(aiTrackedSnapshot(form, ''), baselineSnapshot)) {
              // The read changes what the review goes on (the page's extract is part of it): a form that is unchanged since it was opened is
              // still unchanged. Without this, leaving a field without changing anything would start a review.
              var opened = baselineSnapshot;
              baselineSnapshot = aiTrackedSnapshot(form, extractKey());
              if (lastAiSnapshot && snapshotsEqual(lastAiSnapshot, opened)) lastAiSnapshot = baselineSnapshot;
            }
          } else {
            landingPage.status = 'failed';
            flow('landing', 'failed', t('flow_landing_failed'));
            var why = firstErrorMessage(payload.error);
            landingNotice(why ? t('landing_notice_failed', { reason: /[.!?]$/.test(why) ? why : why + '.' }) : t('landing_notice_failed_plain'),
              t('landing_retry'), function () { readLandingPage(url, true); });
            if (rereadButton) rereadButton.hidden = false;   // so that it can be tried again
          }
        })
        .catch(function () {
          if (landingPage.url !== url) return;
          landingPage.status = 'failed';
          if (!quiet) landingNotice(t('landing_notice_failed_plain'), t('landing_retry'), function () { readLandingPage(url, true); });
        })
        .then(function () {
          if (handled || landingPage.url !== url) return;
          if (quiet) {
            if (!landingPage.reviewWanted) return;   // read ahead of time and nobody has asked: done
            suggestionNotice.setBusy('');
            runAiCheck(false);                       // the editor asked while it was read
            return;
          }
          suggestionNotice.setBusy('');   // the review sets its own, if it runs
          // Exactly one review after the read resolves, either way. The
          // snapshot now carries a different extractKey, so this runs even if
          // a review already happened while the page was being read.
          runAiCheck(!fresh);
        });
    }

    function syncLandingPage() {
      var url = landingPageUrl();
      if (url === landingPage.url) return;
      if (!url) { landingPage = { url: '', status: 'idle', extract: null }; clearLandingNotice(); flow('landing', 'none', ''); showLandingAge(''); return; }
      readLandingPage(url);
    }

    function runAiCheck(auto) {
      if (aiCheckInFlight) { aiCheckQueued = true; return; }
      // A manual run replaces the box; ask first if the editor has changed a suggestion in it.
      var current = stack.latest('ai');
      if (!auto && current && hasPendingEdit(current.body) && typeof window !== 'undefined' &&
          typeof window.confirm === 'function' && !window.confirm(t('replace_edited'))) return;

      // Don't spend a review on a draft we're about to re-review with the
      // page. Deferring beats queueing: it costs one call, not two.
      // A click waits too (2026-10-01): a review without the page gave
      // only a title suggestion. The read starts the review itself.
      if (landingPage.status === 'reading') {
        aiStatus.textContent = t('reading_landing_page');
        landingPage.reviewWanted = true;   // a read made ahead of time then runs the review when it is done
        return;
      }

      // Never replace a suggestion the editor is in the middle of editing (the refresh would erase it).
      if (auto && hasPendingEdit(stackHost)) {
        aiStatus.textContent = t('edit_kept');
        return;
      }

      var snapshot = aiTrackedSnapshot(form, extractKey());
      if (auto && !autoCheckNeeded(snapshot, lastAiSnapshot, baselineSnapshot)) return;

      aiCheckInFlight = true;
      aiButton.disabled = true;
      var runningText = auto
        ? t('ai_updating')
        : t('ai_running');
      aiStatus.textContent = runningText;
      suggestionNotice.setBusy(t('busy_reviewing'));
      if (!landingPageUrl()) flow('landing', 'none', t('flow_landing_none'));
      flow('ai', 'active', t('flow_ai_running'));
      flow('review', 'waiting', '');
      var reviewBody = { dataset: draftForPanel(form, panel), fresh: !auto };
      if (landingPage.extract) reviewBody.landing_page_extract = landingPage.extract;
      postJob('review', reviewBody, form, function (job) {
        aiStatus.textContent = progressText(runningText)(job);
        flow('ai', 'active', progressText(t('flow_ai_running'))(job));
      })
        .then(function (payload) {
          if (!payload.success) {
            throw new Error(firstErrorMessage(payload.error) || t('ai_failed'));
          }
          lastAiSnapshot = snapshot;
          aiStatus.textContent = t('ai_done');
          flow('ai', 'done', t('flow_ai_done'));
          flow('review', 'active', t('flow_review'));
          // A new run replaces the previous AI box (one box per kind) and says so.
          var set = stack.add('ai', t('set_ai'));
          set.snapshot = snapshot;
          renderAIResults(set.body, payload.result, form, aiStatus, suggestionNotice.used);
          if (set.replaced) aiStatus.textContent = t('set_replaced', { time: set.time, old: set.previousTime });
          if (!auto) {
            stack.bringToTop(set);
            stack.reveal(set.element);
          }
          if (set.replaced) flashSet(set.element);
          suggestionNotice.setPending((payload.result.suggestions || []).length);
          var suggestionCount = (payload.result.suggestions || []).length;
        })
        .catch(function (error) {
          flow('ai', 'failed', t('flow_ai_failed'));
          // The generic message is already the whole sentence; do not wrap it in itself.
          aiStatus.textContent = error.message === t('ai_failed') ?
            error.message : t('ai_failed_detail', { error: error.message });
        })
        .finally(function () {
          aiCheckInFlight = false;
          aiButton.disabled = false;
          suggestionNotice.setBusy('');
          if (aiCheckQueued) {
            aiCheckQueued = false;
            runAiCheck(true);
          }
        });
    }

    // A review prepared in advance (ckan metadata-assistant review-all) is shown when the page opens. It is
    // looked up, not asked for: no AI call, and nothing is applied until the editor uses a suggestion.
    function showPrepared() {
      var datasetId = panel.dataset && panel.dataset.datasetId;
      if (!datasetId) return;
      postJob('review', { id: datasetId, cache_only: true }, form)
        .then(function (payload) {
          if (!payload.success || payload.none || !payload.result || stack.latest('ai')) return;
          if (!snapshotsEqual(aiTrackedSnapshot(form, ''), baselineSnapshot)) return;   // edited meanwhile
          lastAiSnapshot = baselineSnapshot;
          var set = stack.add('ai', t('set_ai'));
          set.snapshot = baselineSnapshot;
          renderAIResults(set.body, payload.result, form, aiStatus, suggestionNotice.used);
          var made = payload.prepared_at ? new Date(payload.prepared_at) : null;
          aiStatus.textContent = t('prepared_at', {
            time: made && !isNaN(made) ? (made.toDateString() === new Date().toDateString() ?
              made.toLocaleTimeString(pageLanguage(), { hour: '2-digit', minute: '2-digit' }) :
              made.toLocaleString(pageLanguage(), { dateStyle: 'short', timeStyle: 'short' })) : ''
          });
          suggestionNotice.setPending((payload.result.suggestions || []).length);
          flow('ai', 'done', aiStatus.textContent);
          flow('review', 'active', t('flow_review'));
        })
        .catch(function () { /* nothing prepared is not an error */ });
    }
    showPrepared();

    // The sysadmin's setting "read the landing page when the form opens": the page is read in the background now, so that the
    // suggestions come sooner when they are asked for (they wait for the read otherwise).
    if (panel.dataset && panel.dataset.readPageOnOpen === 'true') {
      var openUrl = landingPageUrl();
      if (openUrl && /^https:\/\//i.test(openUrl) && landingPage.status === 'idle') readLandingPage(openUrl, false, true);
    }

    if (rereadButton) {
      rereadButton.addEventListener('click', function () {
        var url = landingPageUrl();
        if (!url) { aiStatus.textContent = t('reread_no_url'); return; }
        if (landingPage.status === 'reading') return;
        readLandingPage(url, true);   // a fresh read, then a fresh review that uses it
      });
    }

    aiButton.addEventListener('click', function () {
      syncLandingPage();   // a URL just pasted, not yet left: read it first
      var latestSet = stack.latest('ai');
      if (landingPage.status !== 'reading' && sameAsLastRun(latestSet)) {
        stack.present(latestSet, function () { runAiCheck(false); });
        return;
      }
      runAiCheck(false);
    });

    function scheduleAutoCheck() {
      if (autoCheckTimer) clearTimeout(autoCheckTimer);
      autoCheckTimer = setTimeout(function () { runAiCheck(true); }, 600);
    }

    form.addEventListener('focusout', function (event) {
      var name = event.target && event.target.name;
      // Only the main-language fluent input counts as the tracked field.
      var base = fluentBaseName(name);
      if (base && fieldControl(form, base) === event.target) name = base;
      if (AI_TRACKED_FIELDS.indexOf(name) === -1) return;
      if (name === 'url' && landingPageUrl() === lastUrlSeen) return;   // left the field unchanged: nothing to read
      if (name === 'url') {
        lastUrlSeen = landingPageUrl();
        // A new landing page is the one thing worth a managed fetch. It also
        // schedules the follow-up review itself, so don't double up here.
        var before = landingPage.url;
        syncLandingPage();
        if (landingPage.url !== before) return;
      }
      scheduleAutoCheck();
    });

    // tag_string and theme are enhanced with select2, whose search box sits
    // inside the widget instead of on the original element, so a plain
    // "focusout" on the real field does not always fire. select2 itself
    // reports when its dropdown closes, on the original element, which is
    // a more reliable signal for those two fields.
    if (typeof window !== 'undefined' && window.jQuery) {
      window.jQuery(form).on('select2:close', function (event) {
        var name = event.target && event.target.name;
        if (AI_TRACKED_FIELDS.indexOf(name) === -1) return;
        scheduleAutoCheck();
      });
    }
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
      document.querySelectorAll('[data-metadata-assistant-review]').forEach(initialize);
    });
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      firstErrorMessage: firstErrorMessage,
      addressChanges: addressChanges,
      autoCheckNeeded: autoCheckNeeded,
      visibleRemoved: visibleRemoved,
      codeMirrorBox: codeMirrorBox,
      orderLikeTheForm: orderLikeTheForm,
      diffChanges: diffChanges,
      revertChange: revertChange,
      mdWrap: mdWrap,
      mdPrefixLines: mdPrefixLines,
      mdCycleHeading: mdCycleHeading,
      mdLink: mdLink,
      diffWords: diffWords,
      diffSummary: diffSummary,
      autosize: autosize,
      scrollDeltaToReveal: scrollDeltaToReveal,
      orderSets: orderSets,
      newKeywordsOnly: newKeywordsOnly,
      hasPendingEdit: hasPendingEdit,
      unusedSuggestionButtons: unusedSuggestionButtons,
      showToast: showToast,
      linkParts: linkParts,
      currentFieldText: currentFieldText,
      withEditedValue: withEditedValue,
      isBlankSuggestion: isBlankSuggestion,
      applySuggestion: applySuggestion,
      pendingSuggestionsText: pendingSuggestionsText,
      suggestionDisplayText: suggestionDisplayText,
      applyTranslation: applyTranslation,
      hasTranslationTargets: hasTranslationTargets,
      capitalize: capitalize,
      fluentBaseName: fluentBaseName,
      formDraft: formDraft,
      requestHeaders: requestHeaders,
      shouldWarnAboutLandingPage: shouldWarnAboutLandingPage,
      landingPageExtractKey: landingPageExtractKey,
      snapshotsEqual: snapshotsEqual,
      rulesSummary: rulesSummary,
      ageText: ageText,
      postJob: postJob,
      progressText: progressText,
      t: t,
      setStrings: setStrings,
      STRINGS: STRINGS
    };
  }
}());
