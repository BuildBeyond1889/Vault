"""The pack list, the downloaders and the program, checked without downloading anything."""
import csv, glob, os, py_compile, re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PACKS = list(csv.DictReader(open(os.path.join(ROOT, "tools", "packs.csv"), encoding="utf-8"), delimiter="|"))
SHAREABLE = {"green", "yellow"}


def test_pack_list_is_complete():
    assert len(PACKS) >= 150
    for p in PACKS:
        assert p["path"] and p["title"] and p["shelf"] and p["kind"] in ("kiwix", "rachel"), p
        assert p["verdict"] in ("green", "yellow", "orange", "grey"), p
        assert int(p["mb"]) > 0, p


def test_sets_download_only_shareable_packs():
    """The Get files download only packs that are legal to hand out (public domain, open or non-commercial).
    Packs that need permission stay in the list for personal use through Choose Packs, with a warning."""
    ps1 = open(os.path.join(ROOT, "tools", "get-vault.ps1"), encoding="utf-8").read()
    assert re.search(r"function Shareable\(\$it\) \{ \$it\.verdict -eq 'green' -or \$it\.verdict -eq 'yellow' \}", ps1)
    run_set = ps1[ps1.index("function Run-Set"):ps1.index("function Parse-Numbers")]
    assert "(InSet $_ $name) -and (Shareable $_)" in run_set
    assert any(p["verdict"] in SHAREABLE for p in PACKS if "pocket" in p["sets"].split())


def test_every_get_file_names_a_real_set():
    sets = {s for p in PACKS for s in p["sets"].split()}
    for bat in glob.glob(os.path.join(ROOT, "Get - *.bat")):
        m = re.search(r"-Set (\S+)", open(bat, encoding="utf-8").read())
        assert m, bat
        name = m.group(1).lower()
        assert name in sets or name in ("all", "big", "everything"), f"{os.path.basename(bat)} asks for '{name}'"


def test_licence_list_covers_every_pack():
    text = open(os.path.join(ROOT, "PACK-LICENSES.md"), encoding="utf-8").read()
    missing = [p["title"] for p in PACKS if p["title"] not in text]
    assert not missing, missing[:5]


def test_python_compiles(tmp_path):
    for f in glob.glob(os.path.join(ROOT, "tools", "*.py")):
        py_compile.compile(f, cfile=str(tmp_path / (os.path.basename(f) + "c")), doraise=True)


def test_every_language_has_every_word():
    """Each translation in the search page has the same keys as English."""
    page = open(os.path.join(ROOT, "web", "search.html"), encoding="utf-8").read()
    blocks = dict(re.findall(r"\n\s*(en|sw|fr|es|pt|ar|hi|zh)\s*:\s*\{(.*?)\n\s*\}", page, re.S))
    if not blocks:
        return
    keys = lambda b: set(re.findall(r"(\w+)\s*:", b))
    for lang, body in blocks.items():
        assert keys(blocks["en"]) <= keys(body) | {"note"}, f"{lang} is missing {sorted(keys(blocks['en']) - keys(body))[:5]}"
