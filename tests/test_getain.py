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
