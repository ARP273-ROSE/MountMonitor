""":getain# read as the 10Micron protocol 3.2.5 describes it."""
from src.core.lx200_protocol import apply_getain, parse_getain
from src.models.mount_data import EnvironmentSample


def test_full_reply():
    info = parse_getain("359.9512,+48.8732,0.0312,123.45,-0.0021,+0.25,-0.10,18,4.6#")
    assert info == {'polar_error_deg': 0.0312, 'orthogonality_deg': -0.0021, 'terms': 18, 'rms': 4.6}


def test_fields_not_computed_and_too_few_stars():
    info = parse_getain("180.0000,+45.0000,0.1000,010.00,E,E,E,E,E#")
    assert info['polar_error_deg'] == 0.1 and info['terms'] is None and info['rms'] is None
    assert parse_getain("E#") == {} and parse_getain(None) == {}


def test_sample_filled():
    s = EnvironmentSample()
    apply_getain("010.0000,+49.0000,0.0500,090.00,+0.0010,+0.10,+0.20,12,7.3#", s)
    assert (s.alignment_stars, s.alignment_rms, s.polar_error_deg) == (12, 7.3, 0.05)


def test_real_gm3000_reply():
    # reply of a GM3000HPS, fw 3.2.5, sent by the MM3 author (22/11/2026)
    info = parse_getain("359.9966,+52.5324,00.0082,165.14,+00.0124,-00.01,-00.01,22,00003.5#")
    assert info == {'polar_error_deg': 0.0082, 'orthogonality_deg': 0.0124, 'terms': 22, 'rms': 3.5}
