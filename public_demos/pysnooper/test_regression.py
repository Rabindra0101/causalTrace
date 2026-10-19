from types import SimpleNamespace
from subject import get_source_from_frame

def test_source_without_encoding_cookie_is_utf8(tmp_path):
    path = tmp_path / 'unicode.py'
    text = "message = '失败'"
    path.write_text(text, encoding='utf-8')
    frame = SimpleNamespace(f_globals={'__name__': 'unicode_demo'}, f_code=SimpleNamespace(co_filename=str(path)))
    assert get_source_from_frame(frame) == [text]
