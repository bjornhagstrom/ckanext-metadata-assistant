"""Interface texts in more than one language (2026-10-01).

English is the source; ``i18n/sv`` and ``i18n/sv_SE`` hold Swedish. Two things go wrong
silently, so they are tested here: a string in the code that never reaches
the catalogue (it then shows in English on a Swedish page), and a script
text whose key the panel template does not pass on.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "ckanext" / "metadata_assistant"


def test_every_extracted_string_is_translated(tmp_path):
    pot = tmp_path / "extracted.pot"
    env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    subprocess.run(
        [sys.executable, "-m", "babel.messages.frontend", "extract",
         "-F", "babel.cfg", "-o", str(pot), "."],
        cwd=str(ROOT), env=env, capture_output=True, text=True, check=True,
    )
    with pot.open("rb") as f:
        extracted = {m.id for m in read_po(f) if m.id}
    assert len(extracted) > 50, "extraction found too little; a template may have failed to parse"

    for po_path in sorted((PACKAGE / "i18n").glob("*/LC_MESSAGES/*.po")):
        with po_path.open("rb") as f:
            translated = {m.id for m in read_po(f) if m.id and m.string}
        missing = sorted(extracted - translated, key=str)
        assert not missing, f"{po_path.parent.parent.name} lacks: {missing}"


def test_the_panel_passes_every_script_text():
    script = (PACKAGE / "assets" / "js" / "review.js").read_text(encoding="utf-8")
    block = re.search(r"var STRINGS = \{(.*?)\n  \};", script, re.S).group(1)
    in_script = dict(re.findall(r"^\s+(\w+): '((?:[^'\\]|\\.)*)'", block, re.M))

    template = (PACKAGE / "templates" / "metadata_assistant" / "snippets"
                / "review_panel.html").read_text(encoding="utf-8")
    in_template = {
        key: text[1:-1] for key, text in
        re.findall(r"'(\w+)': _\(((?:'[^']*')|(?:\"[^\"]*\"))\)", template)}

    assert in_template == in_script
