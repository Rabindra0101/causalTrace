import ast, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
cache=root/'.causaltrace/public_upstream'
out=root/'public_demos'
def extract(filename,names):
 s=(cache/filename).read_text(encoding='utf-8'); nodes=ast.parse(s).body
 return '\n\n'.join(ast.get_source_segment(s,n) for n in nodes if getattr(n,'name',None) in names or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets))+'\n'
def save(name,source,test,old,new,project,revision):
 d=out/name; d.mkdir(parents=True,exist_ok=True)
 (d/'subject.py').write_text(source,encoding='utf-8')
 (d/'test_regression.py').write_text(test,encoding='utf-8')
 (d/'LICENSE').write_text((cache/(name+'_LICENSE')).read_text(encoding='utf-8'),encoding='utf-8')
 (d/'replay.json').write_text(json.dumps(dict(name=project,path='subject.py',fixed=new,broken=old,upstream_fixed=revision,source=json.loads((cache/'urls.json').read_text())[name+'_fixed.py'],note='Focused extracted source with compatibility harness; newly authored regression test. Three-commit replay history is reconstructed, not upstream history.'),indent=2),encoding='utf-8')
save('humanize','from __future__ import annotations\n'+extract('humanize_fixed.py',{'metric','scientific','_format_not_finite','_SUPERSCRIPT_MAP','_SUPERSCRIPT_TRANS'}),"from subject import metric\n\ndef test_metric_preserves_significant_figures():\n    assert metric(9.999e30, 'W') == '10.0 QW'\n",'exponent < 30','exponent < 32','humanize — significant figures','3690ec5a31b3cd4e2d3374198cf19f7023d3d72d')
save('pysnooper','import re\nfrom types import SimpleNamespace\npycompat = SimpleNamespace(text_type=str)\nutils = SimpleNamespace(file_reading_errors=(OSError,))\n'+extract('pysnooper_fixed.py',{'UnavailableSource','source_cache','ipython_filename_pattern','get_source_from_frame'}),'''from types import SimpleNamespace
from subject import get_source_from_frame

def test_source_without_encoding_cookie_is_utf8(tmp_path):
    path = tmp_path / 'unicode.py'
    text = "message = '失败'"
    path.write_text(text, encoding='utf-8')
    frame = SimpleNamespace(f_globals={'__name__': 'unicode_demo'}, f_code=SimpleNamespace(co_filename=str(path)))
    assert get_source_from_frame(frame) == [text]
''',"encoding = 'ascii'","encoding = 'utf-8'",'PySnooper — Unicode source','56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2')
save('cookiecutter','import os, json, logging\nfrom collections import OrderedDict\nlogger = logging.getLogger(__name__)\nclass ContextDecodingException(ValueError):\n    pass\n\n'+extract('cookiecutter_fixed.py',{'generate_context','apply_overwrites_to_context'}),'''import builtins
import subject

def test_context_decoding_is_locale_independent(tmp_path, monkeypatch):
    path = tmp_path / 'cookiecutter.json'
    path.write_text('{"city": "北京"}', encoding='utf-8')
    def locale_open(path, **kwargs):
        kwargs.setdefault('encoding', 'ascii')
        return builtins.open(path, **kwargs)
    monkeypatch.setattr(subject, 'open', locale_open, raising=False)
    assert subject.generate_context(str(path))['cookiecutter']['city'] == '北京'
''',"open(context_file)","open(context_file, encoding='utf-8')",'Cookiecutter — UTF-8 context','7f6804c4953a18386809f11faf4d86898570debc')
d=out/'commons_csv'; d.mkdir(parents=True,exist_ok=True)
p='src/main/java/org/apache/commons/csv/ExtendedBufferedReader.java'
(d/p).parent.mkdir(parents=True,exist_ok=True)
(d/p).write_text((cache/'csv_fixed.java').read_text(encoding='utf-8'),encoding='utf-8')
t=d/'src/test/java/org/apache/commons/csv/CarriageReturnTest.java';t.parent.mkdir(parents=True,exist_ok=True)
t.write_text('''package org.apache.commons.csv;
import java.io.StringReader;
import org.junit.Test;
import static org.junit.Assert.assertEquals;
public class CarriageReturnTest {
 @Test public void countsCarriageReturnSeparators() throws Exception {
   ExtendedBufferedReader reader = new ExtendedBufferedReader(new StringReader("a\\rb\\rc"));
   while (reader.read() != -1) { }
   assertEquals(2, reader.getLineNumber());
 }
}
''',encoding='utf-8')
(d/'pom.xml').write_text((root/'tests/fixtures/multilang/pom.xml').read_text(),encoding='utf-8')
for f in ('LICENSE','NOTICE'):(d/f).write_text((cache/('csv_'+f)).read_text(encoding='utf-8'),encoding='utf-8')
(d/'replay.json').write_text(json.dumps(dict(name='Apache Commons CSV — CR line counting',path=p,fixed="current == '\\r' || (current == '\\n' && lastChar != '\\r')",broken="current == '\\n'",upstream_fixed='de1838ea067f3fbc4c7c21b9eeae077c739ecb73',source=json.loads((cache/'urls.json').read_text())['csv_fixed.java'],note='Complete upstream reader class, newly authored JUnit test; reconstructed history for Defects4J Csv-1 / CSV-75.'),indent=2),encoding='utf-8')
# Record both original revisions and a checksum of the complete downloaded source.
import hashlib
pins = {
 'humanize': '392aef707c0e74341ab4a51420984e9ea6b566c5',
 'pysnooper': 'e21a31162f4c54be693d8ca8260e42393b39abd3',
 'cookiecutter': 'c15633745df6abdb24e02746b82aadb20b8cdf8c',
 'commons_csv': '0833f45bffd40f44ba6f294d84e9bac8a9ba0a37',
}
for name, revision in pins.items():
    manifest = out / name / 'replay.json'
    info = json.loads(manifest.read_text(encoding='utf-8'))
    upstream = cache / ('csv_fixed.java' if name == 'commons_csv' else name + '_fixed.py')
    info['upstream_buggy'] = revision
    info['upstream_source_sha256'] = hashlib.sha256(upstream.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(info, indent=2), encoding='utf-8')
