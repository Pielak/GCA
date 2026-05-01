from app.gatekeeper.checks.exception_handling import check_source


def test_bare_except_detected():
    code = "try:\n    x()\nexcept:\n    pass\n"
    issues = check_source(code)
    codes = {i["code"] for i in issues}
    assert "EH001" in codes


def test_blind_except_without_raise_detected():
    code = "try:\n    x()\nexcept Exception:\n    print('oops')\n"
    issues = check_source(code)
    assert any(i["code"] == "EH002" for i in issues)


def test_blind_except_with_raise_passes():
    code = (
        "try:\n    x()\nexcept Exception as e:\n"
        "    logger.exception('failed')\n    raise\n"
    )
    issues = check_source(code)
    assert not any(i["code"] == "EH002" for i in issues)


def test_pass_silencioso_detected():
    code = "try:\n    x()\nexcept ValueError:\n    pass\n"
    issues = check_source(code)
    assert any(i["code"] == "EH003" for i in issues)


def test_return_none_silencioso_detected():
    code = "def f():\n    try:\n        return x()\n    except ValueError:\n        return None\n"
    issues = check_source(code)
    assert any(i["code"] == "EH004" for i in issues)


def test_specific_except_with_raise_passes():
    code = (
        "try:\n    x()\nexcept ValueError as e:\n"
        "    logger.exception('bad value')\n"
        "    raise DomainError('invalid') from e\n"
    )
    issues = check_source(code)
    assert issues == []
