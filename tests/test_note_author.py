"""Author type is read from the signature, not from a body mention of another clinician."""

from services.note_author import EPILEPTOLOGIST, NURSE, OTHER, TRAINEE, UNKNOWN, note_author


def test_signature_roles():
    assert note_author("Yours sincerely\nDr A Smith\nConsultant Neurologist") == EPILEPTOLOGIST
    assert note_author("Yours\nJane Doe\nEpilepsy Specialist Nurse") == NURSE
    assert note_author("Kind regards\nDr B\nSpecialty trainee in neurology") == TRAINEE
    assert note_author("Yours\nDr C\nGeneral neurologist") == OTHER


def test_body_mention_of_nurse_is_not_the_author():
    text = ("I will ask the epilepsy nurse to contact Mrs Williams.\n"
            "I will see her again in six months.\nYours sincerely\nDr Smith\nConsultant Neurologist")
    assert note_author(text) == EPILEPTOLOGIST
    assert note_author("I will ask the epilepsy nurse to contact her in a few months.") == UNKNOWN


def test_unsigned_letter_is_unknown():
    assert note_author("I reviewed this man in clinic today. He remains seizure free.") == UNKNOWN
