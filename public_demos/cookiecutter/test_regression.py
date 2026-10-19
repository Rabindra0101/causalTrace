import builtins
import subject

def test_context_decoding_is_locale_independent(tmp_path, monkeypatch):
    path = tmp_path / 'cookiecutter.json'
    path.write_text('{"city": "北京"}', encoding='utf-8')
    def locale_open(path, **kwargs):
        kwargs.setdefault('encoding', 'ascii')
        return builtins.open(path, **kwargs)
    monkeypatch.setattr(subject, 'open', locale_open, raising=False)
    assert subject.generate_context(str(path))['cookiecutter']['city'] == '北京'
