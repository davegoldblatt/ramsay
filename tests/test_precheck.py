from ramsay.precheck import find_dossier_line, run_precheck
from ramsay.style import load_rubric

DOSSIER = """Hi Sam,

Acme's Dayton plant builds hydraulic valves.

We make a small sensor. Your best tech wears it during a setup and talks through it, and it writes the procedure.

Worth 15 minutes next week?"""

FOLDED_HYPHEN = """Hi Sam,

Acme's Dayton plant builds hydraulic valves-we make a small sensor. Your best tech wears it during a setup and talks through it, and it writes the procedure.

Worth 15 minutes next week?"""

FOLDED_RUN_ON = """Hi Sam,

Acme's Dayton plant builds hydraulic valves, but the sensor is what we make. Your best tech wears it during a setup.

Worth 15 minutes next week?"""

CUT = """Hi Sam,

We make a small sensor. Your best tech wears it during a setup and talks through it.

Worth 15 minutes next week?"""

QUESTION_OPENER = """Hi Sam,

Who covers the leak test when your senior tech is out?

If nobody, that's the job we built the sensor for."""

SENDER_VOICE_OPENER = """Hi Sam,

Our laser engraver prints wavy lines unless someone jams sticky notes into one corner.

Is there a fix like that on your floor?"""

SINGLE_PARAGRAPH = """Hi Sam,

Should I check back in the spring, or leave it?"""

NO_GREETING_TWO_SENTENCES = """The recordings stay encrypted on the device. You can keep the decrypting computer in a locked office.

Would your IT group want that in writing?"""


def test_dossier_line_detected():
    assert find_dossier_line(DOSSIER) == "Acme's Dayton plant builds hydraulic valves."


def test_folded_or_cut_facts_pass():
    for text in (FOLDED_HYPHEN, FOLDED_RUN_ON, CUT):
        assert find_dossier_line(text) is None


def test_openers_that_do_work_pass():
    for text in (QUESTION_OPENER, SENDER_VOICE_OPENER, SINGLE_PARAGRAPH, NO_GREETING_TWO_SENTENCES):
        assert find_dossier_line(text) is None


def test_precheck_flag_off_by_default():
    assert run_precheck(DOSSIER).passed


def test_precheck_flag_on_fails_with_reason():
    result = run_precheck(DOSSIER, check_dossier_line=True)
    assert not result.passed
    assert result.failures[0].startswith("Dossier line standing alone")


def test_bare_hyphen_is_not_an_em_dash():
    assert run_precheck(FOLDED_HYPHEN, check_dossier_line=True).passed


def test_email_rubric_turns_check_on():
    assert load_rubric("email").check_dossier_line is True
    assert load_rubric("essay").check_dossier_line is False
