from alpha.pyguard import check_python


def test_old_python_gets_fix_hint():
    msg = check_python((3, 9))
    assert msg is not None
    assert "3.11+" in msg
    assert "found 3.9" in msg
    assert "uv python install" in msg


def test_new_python_passes():
    assert check_python((3, 11)) is None
