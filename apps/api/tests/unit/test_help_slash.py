from app.application.help_slash import parse_help_slash


def test_help_english() -> None:
    r = parse_help_slash("/help куда ходит :443?")
    assert r.is_help
    assert r.text == "куда ходит :443?"


def test_help_russian() -> None:
    r = parse_help_slash("/помощь  порты стенда")
    assert r.is_help
    assert r.text == "порты стенда"


def test_not_help() -> None:
    r = parse_help_slash("просто вопрос")
    assert not r.is_help
    assert r.text == "просто вопрос"
