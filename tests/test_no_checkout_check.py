"""The no-checkout check: what it flags in a skill body, and what it leaves."""

from __future__ import annotations

import pytest
from _no_checkout import LINK_PREFIX, local_repository_paths
from test_skills_references import RAW, SKILLS


@pytest.mark.criterion(id="c3")
def test_the_no_checkout_check_flags_root_files_absolute_paths_and_windows_homes_c3() -> None:
    body = (
        "# Skill\n\n"
        "1. Read README.md for the options.\n"
        "2. Open CHANGELOG.md before you start.\n"
        "3. Copy the file to /srv/periplus/map.json.\n"
        "4. Or open C:\\Users\\someone\\periplus\\map.json.\n"
        "5. Check uv.lock for the pins.\n"
        "6. Read the rule format in src/periplus/rutters/php/rutter.yaml.\n"
        "7. Then open ~/workspace/periplus/rutter.yaml.\n"
        "8. Or open $HOME/workspace/periplus/rutter.yaml.\n"
        "9. Or open periplus/src/periplus/packs/php_basic@0.2.0/pack.yaml.\n"
        "10. Check pyproject.toml for the version.\n"
        "11. Or copy it to /tmp./srv/map.json.\n"
    )
    flagged = local_repository_paths({"periplus-bad": body})
    assert "periplus-bad: README.md" in flagged
    assert "periplus-bad: CHANGELOG.md" in flagged
    assert any(p.startswith("periplus-bad: /srv/periplus") for p in flagged), flagged
    assert any(p.startswith("periplus-bad: C:\\Users") for p in flagged), flagged
    assert "periplus-bad: uv.lock" in flagged
    assert "periplus-bad: src/periplus/rutters/php/rutter.yaml" in flagged
    assert "periplus-bad: ~/workspace/periplus/rutter.yaml" in flagged
    assert "periplus-bad: $HOME/workspace/periplus/rutter.yaml" in flagged
    assert "periplus-bad: periplus/src/periplus/packs/php_basic@0.2.0/pack.yaml" in flagged
    assert "periplus-bad: pyproject.toml" in flagged
    assert "periplus-bad: /tmp./srv/map.json" in flagged


@pytest.mark.criterion(id="c3")
def test_the_no_checkout_check_leaves_own_folder_temp_and_pinned_links_and_shipped_skills_c3() -> (
    None
):
    body = (
        "# Skill\n\n"
        "1. Run python ${CLAUDE_SKILL_DIR}/scripts/gaps.py on the map.\n"
        "2. Write the report to /tmp/periplus-report.txt.\n"
        f"3. See [Navigation]({LINK_PREFIX}docs/navigation.md) for the options.\n"
        "4. Open SKILL.md again.\n"
        "5. Read README.md for the options.\n"
        "6. Keep a copy in /tmp/periplus/<project folder>/before.json.\n"
        "7. Or open <project folder>/map.json.\n"
    )
    flagged = local_repository_paths({"periplus-ok": body})
    assert flagged == ["periplus-ok: README.md"], flagged
    assert set(RAW) == set(SKILLS)
    assert local_repository_paths(RAW) == []
