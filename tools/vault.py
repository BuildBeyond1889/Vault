"""Archie Vault: browse, search and read an offline library of Kiwix and RACHEL packs.

The vault folder (picked the first time the downloader runs) holds:
  * zim\\     Kiwix .zim files (Wikipedia, Stack Exchange sites, textbooks, maps, storybooks...)
  * rachel\\  RACHEL modules (folders of web pages: Hesperian health guides, GCF LearnFree, W3Schools...)

This module gives Archie:
  * a CATALOGUE: every pack as a card on a subject shelf, with its size, page count, description and icon,
    kids / teens / adults marks, and "new" / "updated" marks when Get Vault brings in something new;
  * each pack's OWN FRONT PAGE, shown exactly as the pack's makers designed it;
  * SEARCH across all packs, one shelf or one pack: page titles first (fast), then inside the pages;
  * a RANDOM page, three pages PICKED FOR TODAY (kids, teens, adults), and RELATED packs;
  * SAVED pages, and flashcards from any page into Study.

Pages are served by a second little web server on its own port, so a page from a pack can never reach Archie's
own controls. Everything reads files on this PC. Nothing goes online.
"""
import datetime
import html as htmllib
import json
import math
import mimetypes
import os
import random
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, wait
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------- shelves, ages and topics

SHELVES = [
    ("core", "Core knowledge", "Encyclopedias, dictionaries, free books, travel and countries"),
    ("health", "Health and medicine", "Medical encyclopedias, field medicine, medicines, animal health"),
    ("land", "Farming, water, energy and survival", "Growing food, clean water, solar and biogas, disasters, old how-to books"),
    ("repair", "Repair, salvage and electronics", "Fixing things, electronics, old PCs and phones, Linux"),
    ("code", "Coding", "Language docs, Stack Overflow, algorithms, game development"),
    ("learn", "Learning for every age", "School to college: textbooks, courses, simulations, storybooks, teaching"),
    ("maps", "Maps", "Offline street maps"),
    ("other", "Other packs", "Packs that aren't in Archie's list"),
]
SHELF_NAME = {k: t for k, t, d in SHELVES}
LETTER_SHELF = {"A": "core", "B": "health", "C": "land", "D": "repair", "E": "code", "F": "learn", "G": "maps"}
BIG_SHELF = [("khanacademy", "learn"), ("stackoverflow.com", "code"), ("gutenberg", "core"), ("survivorlibrary", "land"),
             ("crashcourse", "learn"), ("armypubs", "land"), ("math.stackexchange", "learn"), ("physics.stackexchange", "learn"),
             ("en-learnsaylor", "learn")]

KIDS = ("africanstorybook", "booksdash", "vikidia", "prunelle", "phet_", "en-scratch", "en-blockly", "en-code_monster",
        "en-feed-the-monster", "wikipedia_en-simple", "wiktionary_en-simple", "khanacademy", "libretexts.org_en_k12")
KIDS_ONLY = ("africanstorybook", "booksdash", "prunelle", "en-feed-the-monster", "en-blockly", "en-code_monster", "vikidia")
TEENS = ("khanacademy", "phet_", "en-ck12", "en-siyavula", "libretexts.org_en_k12", "artofproblemsolving", "crashcourse",
         "ncase.me", "freecodecamp", "wikipedia_en-simple", "wiktionary", "en-scratch", "en-w3schools", "en-tanzanian_exams",
         "en-rasyti_typing", "phzh_core-english", "gutenberg", "wikipedia_en_all", "wikipedia_sw", "wikivoyage", "htdp",
         "lua.org", "theworldfactbook", "devdocs_en_python", "devdocs_en_godot", "devdocs_en_javascript", "devdocs_en_html",
         "devdocs_en_css", "gamedev.stackexchange", "arduino.stackexchange", "raspberrypi.stackexchange",
         "robotics.stackexchange", "3dprinting.stackexchange", "en-openstax", "libretexts.org_en_math",
         "libretexts.org_en_phys", "libretexts.org_en_bio", "libretexts.org_en_chem", "math.stackexchange",
         "physics.stackexchange", "ell.stackexchange", "wikibooks", "wikiversity", "opendatastructures", "jeffe.cs",
         "ifixit", "en-gcf", "cs.stackexchange", "zimgit-knots", "gardenology")

TAGS = [   # (tag, words in the file name or title) -> related packs share tags
    ("encyclopedia", ("wikipedia", "vikidia", "wikimed", "mdwiki", "encyclopedia")),
    ("dictionary", ("wiktionary", "dictionary")),
    ("swahili", ("_sw_", "_sw.", "swahili")),
    ("books", ("gutenberg", "wikisource", "wikibooks", "storybook", "booksdash", "prunelle", "textbook", "openstax", "libretexts", "milne")),
    ("kids-reading", ("storybook", "booksdash", "prunelle", "feed-the-monster", "vikidia", "simple")),
    ("medicine", ("medic", "mdwiki", "wikem", "medline", "nhs.uk", "cdc.gov", "hesperian", "skin-of-color", "asst_medical", "libretexts.org_en_med")),
    ("animals", ("wikivet", "infonet")),
    ("farming", ("garden", "infonet", "farming", "food-preparation", "usda", "survivorlibrary", "cd3wd", "appropedia")),
    ("water", ("water", "post-disaster", "appropedia", "cd3wd", "practical_action")),
    ("energy", ("energypedia", "lowtechmagazine", "appropedia", "solar", "sustainab")),
    ("survival", ("prepper", "ready.gov", "outdoors", "armypubs", "military", "post-disaster", "knots", "survivorlibrary")),
    ("repair", ("ifixit", "restarters", "diy.stackexchange", "mechanics", "bicycles", "woodworking", "home improvement")),
    ("electronics", ("electronics", "arduino", "raspberrypi", "robotics", "iot.", "ham.", "3dprinting")),
    ("old-hardware", ("retrocomputing", "permacomputing", "postmarketos", "openwrt", "askubuntu", "superuser", "android")),
    ("linux", ("askubuntu", "unix.stackexchange", "archlinux", "devdocs_en_man", "devdocs_en_bash", "postmarketos", "openwrt")),
    ("coding", ("devdocs", "stackoverflow", "codereview", "softwareengineering", "cs.stackexchange", "freecodecamp", "w3schools",
                "htdp", "lua.org", "opendatastructures", "jeffe", "wikipedia_en_computer", "scratch", "blockly", "code_monster", "cseducators")),
    ("games", ("gamedev", "godot", "pygame", "lua")),
    ("math", ("math", "artofproblemsolving", "khanacademy", "stats", "jeffe", "euler")),
    ("science", ("phet", "physics", "chem", "bio", "geo", "earthscience", "ncase", "crashcourse", "libretexts", "climate", "siyavula", "ck12")),
    ("teaching", ("oer4schools", "teachertraining", "educators", "parenting", "ell.stackexchange", "core-english")),
    ("work-skills", ("workforce", "gcf", "budgeting", "resume", "typing", "biz")),
    ("travel", ("wikivoyage", "factbook", "maps_", "cdc.gov")),
    ("maps", ("maps_",)),
]
TODAY_FROM = {   # where today's picks come from (first ones that exist)
    "kids": ["africanstorybook", "booksdash", "vikidia", "prunelle_en_interactive-books", "wikipedia_en-simple_all"],
    "teens": ["wikipedia_en-simple_all", "ncase.me", "wikipedia_en_all", "libretexts.org_en_k12", "wikibooks_en_all", "wikivoyage"],
    "adults": ["wikipedia_en_all", "wikivoyage_en_all", "appropedia", "solar.lowtechmagazine", "energypedia", "ifixit",
               "gardenology", "theworldfactbook", "wikibooks_en_all"],
}
NOT_READING = ("maps_", "phet_")            # one-page apps: no random pages from these
BAD_TITLE = re.compile(r"^(list of|index of|lists of|category:|template:|file:|user:|portal:|help:|talk:|special:|wikipedia:|outline of)", re.I)
SE_JUNK = re.compile(r"^(user |highest voted |newest |unanswered |questions tagged|frequent )", re.I)

# ---- reading a question: which words matter, and what kind of question it is
STOPWORDS = set("""a an the and or of to in on at by for with from into about as is are was were be been do does did done can could should would
will how what why when where which who whom whose that this these those it its i me my we our you your they them their there here
some any all much many more most very just also so if then than not no yes get got make makes making use using used keep keeps
want need know tell show find way ways best good thing things something work works working happen happens please
cha ya la na wa za kwa ni katika""".split())
KID_WORDS = {"kids", "kid", "toddlers"}
ASPECT_WORDS = set("""symptoms symptom signs sign causes cause treatment treatments treat treating cure prevention prevent types type
history definition diagnosis effects effect uses benefits problems problem facts examples example steps guide basics introduction""".split())
HOWTO_WORDS = set("""fix repair treat make build stop prevent store plant grow install replace tie cook clean purify wire charge
keeps won't wont doesn't broken leaking slipping""".split())
HOWTO_VERBS = {"fix", "repair", "make", "build", "install", "replace", "stop", "prevent", "store", "plant", "grow", "use", "tie", "cook",
               "clean", "purify", "wire", "treat", "keeps", "slipping", "leaking", "broken"}
STORY_WORDS = {"story", "stories", "tale", "tales", "storybook", "book", "books", "read"}
PRACTICAL = ("en-hesperian", "www.ready.gov", "ifixit", "appropedia", "en-practical_action", "en-infonet", "restarters", "wikibooks",
             "energypedia", "zimgit-", "usda-", "wikem", "wwwnc.cdc", "nhs.uk", "stackexchange", "superuser", "askubuntu", "cd3wd")
STORY_PACKS = ("africanstorybook", "booksdash", "prunelle", "gutenberg")
PEOPLE_WORDS = {"children", "child", "adults", "adult", "people", "person", "someone", "elderly"}
SMALL_WORDS = {"of", "the", "and", "in", "a", "an", "to", "for", "on", "at", "by", "or"}


def smart_title(g):
    """'causes of world war i' -> 'Causes of World War I' (how Wikipedia names articles)."""
    ws = g.split()
    return " ".join(w if (i and w in SMALL_WORDS) else (w.upper() if w.lower() in ("i", "ii", "iii") else w[:1].upper() + w[1:]) for i, w in enumerate(ws))


LEAD_WORDS = set("how to what is are was a an the do does did in on should i can could why when where which who whats".split())
DEFINE_WORDS = {"mean", "means", "meaning", "define", "definition"}
CODE_WORDS = set("""python javascript js java c++ cpp csharp c# rust golang kotlin typescript html css json xml sql sqlite api comprehension compile compiler debug syntax git github linux bash terminal regex algorithm algorithms pointer pointers struct godot gdscript unity unreal pygame numpy pandas flask django react node npm arduino esp32 hashmap linked-list hashmap stackoverflow programming coding code""".split())
CODE_PHRASES = ("linked list", "data structure", "binary tree", "hash table", "for loop", "while loop", "stack overflow", "big o", "source code",
                "command line", "web page", "website")
# how much to trust each kind of pack for a general question (key prefix -> weight); anything else is 1.0
PRIOR = [("wikipedia_en_all", 1.25), ("wikipedia_en-simple", 1.15), ("mdwiki", 1.15), ("wikem", 1.15), ("vikidia", 1.0),
         ("appropedia", 1.2), ("energypedia", 1.15), ("en-hesperian", 1.3), ("en-practical_action", 1.15), ("en-infonet", 1.2),
         ("ifixit", 1.2), ("restarters", 1.1), ("www.ready.gov", 1.25), ("zimgit-", 1.15), ("usda-", 1.15), ("wwwnc.cdc", 1.1),
         ("nhs.uk", 1.15), ("medlineplus", 1.15), ("wikivet", 1.15), ("wikibooks", 1.0), ("wikivoyage", 1.0), ("khanacademy", 1.0),
         ("wiktionary", 0.55), ("maps_", 0.45), ("gutenberg", 0.7), ("survivorlibrary", 0.75), ("en-learnsaylor", 0.75), ("en-saylor", 0.8),
         ("libretexts", 0.9), ("wikisource", 0.6), ("ell.stackexchange", 0.7), ("parenting.", 0.8), ("matheducators", 0.7),
         ("cseducators", 0.7), ("trueprepper", 0.85), ("lowtechmagazine", 0.85), ("crashcourse", 0.9)]
TOPIC_PACKS = ("wikipedia_en_all", "wikipedia_en-simple", "mdwiki", "wikem", "vikidia", "wikivoyage", "wikipedia_sw", "appropedia",
               "energypedia", "gardenology")
VULGAR = re.compile(r"(?i)(fuck|shit|cunt|bitch|whore|slut|porn|nigg|faggot|dick\b|cock\b|pussy|tits\b|anal\b|rape)")


def analyze(q):
    """Split a question into the words that matter and what kind of question it is."""
    words = [w.lower() for w in re.findall(r"[\w#+']+", q)]
    words = [w[:-2] if w.endswith("'s") else w for w in words]
    low0 = " ".join(words)
    kids = any(w in KID_WORDS for w in words) or any(ph in low0 for ph in ("for children", "for a child", "for beginners", "for young"))
    define = any(w in DEFINE_WORDS for w in words) and len(words) <= 6
    low = " ".join(words)
    code = any(w in CODE_WORDS for w in words) or any(ph in low for ph in CODE_PHRASES)
    content = [w for w in words if w not in STOPWORDS and w not in KID_WORDS and w not in DEFINE_WORDS and w != "won't" and len(w) > 1]
    if not content:
        content = [w for w in words if len(w) > 2] or words
    howto = any(w in HOWTO_WORDS for w in words) or any(low0.startswith(x) or (" " + x) in low0 for x in
                                                         ("how to ", "how do i", "how can i", "how should i", "what to do", "what should i do"))
    lead = list(words)
    while lead and lead[0] in LEAD_WORDS:
        lead.pop(0)
    subject = [w for w in content if w not in ASPECT_WORDS and w not in STORY_WORDS and w not in PEOPLE_WORDS and w not in HOWTO_VERBS] or content
    return {"words": words, "content": content, "kids": kids, "define": define, "code": code, "clean": " ".join(content) or q,
            "subject": subject, "howto": howto, "story": any(w in STORY_WORDS for w in words),
            "phrase": " ".join(lead)}


def lang_of(key):
    """Language of a pack from its file name: wikipedia_sw_all -> sw; most packs are English."""
    m = re.search(r"_(sw|fr|es|pt|ar|hi|zh|de|mul)[_-]", key + "_")
    return m.group(1) if m else "en"


LANG3 = {"swa": "sw", "fra": "fr", "spa": "es", "por": "pt", "ara": "ar", "hin": "hi", "zho": "zh", "eng": "en"}


def prior_of(key):
    k = key.lower()
    return next((w for pre, w in PRIOR if k.startswith(pre) or pre in k), 1.0)


def stem(w):
    for end in ("ies", "es", "s", "ing", "ed"):
        if len(w) > len(end) + 3 and w.endswith(end):
            return w[:-len(end)] + ("y" if end == "ies" else "")
    return w


def coverage(title, content):
    t = title.lower()
    if not content:
        return 0.0
    return sum(1 for w in content if stem(w)[:6] in t) / len(content)
DATE_TAIL = re.compile(r"_(\d{4}-\d{2})([a-z]?)$")
VARIANT = re.compile(r"_(maxi|nopic|mini)$")


def key_of(stem):
    """wikipedia_en_all_maxi_2026-08 -> wikipedia_en_all_maxi (the same pack across versions)."""
    return DATE_TAIL.sub("", stem)


def date_of(stem):
    m = DATE_TAIL.search(stem)
    return (m.group(1) + m.group(2)) if m else ""


def family_of(key):
    """wikipedia_en_all_maxi / _mini / _nopic are one family: the catalogue shows one card for them."""
    return VARIANT.sub("", key)


def _has(s, words):
    return any(w in s for w in words)


def ages_of(key, shelf):
    k = key.lower()
    out = []
    if _has(k, KIDS):
        out.append("kids")
    if _has(k, TEENS) or (shelf == "code" and not k.startswith(("stackoverflow", "softwareengineering"))):
        out.append("teens")
    if not _has(k, KIDS_ONLY):
        out.append("adults")
    return out


def tags_of(key, title):
    s = (key + " " + title).lower()
    return [t for t, words in TAGS if _has(s, words)]


def gb(n):
    return "%.1f GB" % (n / 1e9) if n >= 1e9 else ("%d MB" % max(1, round(n / 1e6)))


def text_of_html(h, limit=400000):
    """Readable text from a page (scripts, styles, menus and footers dropped)."""
    h = h[:limit]
    for tag in ("main", "article"):      # most sites put the page itself in <main> or <article>: skip their menus
        m = re.search(r"(?is)<%s\b[^>]*>(.*)</%s>" % (tag, tag), h)
        if m and len(m.group(1)) > 400:
            h = m.group(1)
            break
    h = re.sub(r"(?is)<(script|style|noscript|nav|header|footer|svg|math|template|title)\b.*?</\1>", " ", h)
    h = re.sub(r"(?is)<(br|p|div|li|h[1-6]|tr|dd|dt|section|article|pre|blockquote)\b[^>]*>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = htmllib.unescape(h)
    lines = [" ".join(l.split()) for l in h.split("\n")]
    return "\n".join(l for l in lines if l)


def snippet(text, words, size=240):
    low = text.lower()
    best = -1
    for w in words:
        i = low.find(w.lower(), 40 if len(low) > 400 else 0)
        if i >= 0 and (best < 0 or i < best):
            best = i
    if best < 0:
        body = [l for l in text.split("\n") if len(l) > 80]
        s = body[0] if body else text
        return s[:size].strip() + ("..." if len(s) > size else "")
    a = max(0, best - size // 3)
    s = text[a:a + size].replace("\n", " ")
    return ("..." if a else "") + s.strip() + "..."


FRAME_JS = (b"<script>/* Archie Vault */(function(){function tell(){try{parent.postMessage({archieVault:1,href:location.href,"
            b"title:document.title||''},'*')}catch(e){}}if(document.readyState!=='loading')tell();else addEventListener('DOMContentLoaded',tell);"
            b"addEventListener('load',tell);document.addEventListener('click',function(e){var a=e.target&&e.target.closest&&e.target.closest('a');"
            b"if(!a)return;var h=a.getAttribute('href')||'';if(/\\.pdf($|[?#])/i.test(h)||(/^(https?:)?\\/\\//i.test(h)&&a.host!==location.host)){"
            b"a.target='_blank';a.rel='noopener'}},true)})();</script>")
EXTRA_MIME = {".webm": "video/webm", ".mp4": "video/mp4", ".ogv": "video/ogg", ".mp3": "audio/mpeg", ".pdf": "application/pdf",
              ".svg": "image/svg+xml", ".js": "application/javascript", ".css": "text/css", ".woff2": "font/woff2",
              ".woff": "font/woff", ".json": "application/json", ".htm": "text/html", ".html": "text/html", ".swf": "application/x-shockwave-flash"}


# ---------------------------------------------------------------- the vault

class Vault:
    def __init__(self, base_dir, data_dir, get_model=None, study_dir=None, wiki_dir=None, log=None, folder_file=None, csv_path=None):
        self.base = base_dir
        self.folder_file = folder_file      # a text file naming the vault folder (the stand-alone Vault uses this)
        self.csv_path = csv_path            # the pack list (title, shelf, licence...) if it isn't next to the downloader
        self.data = data_dir
        self.get_model = get_model or (lambda: "")
        self.study_dir = study_dir
        self.wiki_dir = wiki_dir
        self.log = log or (lambda *a: None)
        os.makedirs(self.data, exist_ok=True)
        self.icon_dir = os.path.join(self.data, "vault-icons")
        self.lock = threading.Lock()
        self.open = {}                      # path -> [Archive, search lock, last used]
        self.meta = self._load("vault-meta.json", {})
        self.rindex = {}                    # rachel module -> [[path, title]]
        self.pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="vault")
        self.slow = {}                      # pack id -> skip it in "everything" searches until then
        self._scan = None                   # background scan thread
        self._cat = (0, None)
        self.content_port = 0
        self.server = None
        self.csv = self._read_csv()

    # ---------- small file helpers
    def _p(self, name):
        return os.path.join(self.data, name)

    def _load(self, name, default):
        try:
            with open(self._p(name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _save(self, name, obj):
        p = self._p(name)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)

    # ---------- where things are
    def _vault_dirs(self):
        cands = []
        if self.folder_file:
            try:
                with open(self.folder_file, encoding="utf-8-sig") as f:
                    return [f.read().strip().strip('"')]
            except OSError:
                return []
        for d in (os.path.join(self.base, "Vault"), os.path.join(self.base, "vault")):
            try:
                with open(os.path.join(d, "vault-folder.txt"), encoding="utf-8-sig") as f:
                    cands.append(f.read().strip().strip('"'))
            except OSError:
                pass
            cands.append(d)
        return [d for d in cands if d]

    def folder(self):
        for d in self._vault_dirs():
            if os.path.isdir(os.path.join(d, "zim")) or os.path.isdir(os.path.join(d, "rachel")):
                return d
        return ""

    def _read_csv(self):
        out = {}
        paths = [self.csv_path] if self.csv_path else \
            [os.path.join(d, "vault-list.csv") for d in [os.path.join(self.base, "vault"), os.path.join(self.base, "Vault")] + self._vault_dirs()]
        for p in paths:
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8-sig") as f:
                    rows = [l.rstrip("\n").split("|") for l in f]
            except OSError:
                continue
            head = rows[0] if rows else []
            for r in rows[1:]:
                if len(r) != len(head):
                    continue
                row = dict(zip(head, r))
                stem = row.get("path", "").split("/")[-1]
                out[key_of(stem) if row.get("kind") == "kiwix" else stem] = row
            if out:
                break
        return out

    def _files(self):
        """[(id, kind, stem, full path, size, mtime)] for every finished pack."""
        out = []
        root = self.folder()
        zdirs = [os.path.join(root, "zim")] if root else []
        if self.wiki_dir:
            zdirs.append(self.wiki_dir)
        seen = set()
        for zd in zdirs:
            try:
                names = os.listdir(zd)
            except OSError:
                continue
            for f in names:
                if not f.lower().endswith(".zim") or f.lower() in seen:
                    continue
                seen.add(f.lower())
                p = os.path.join(zd, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                out.append((f[:-4], "zim", f[:-4], p, st.st_size, st.st_mtime))
        rd = os.path.join(root, "rachel") if root else ""
        try:
            mods = os.listdir(rd) if rd else []
        except OSError:
            mods = []
        for m in mods:
            top = os.path.join(rd, m)
            if not os.path.isdir(top) or not os.path.exists(os.path.join(top, ".done")):
                continue
            try:
                done = os.path.getmtime(os.path.join(top, ".done"))
            except OSError:
                done = 0
            out.append(("r:" + m, "rachel", m, self._rroot(m, rd), self.meta.get("r:" + m, {}).get("size", 0), done))
        return out

    def _rroot(self, m, rd=None):
        rd = rd or os.path.join(self.folder(), "rachel")
        inner = os.path.join(rd, m, m)
        return inner if os.path.isdir(inner) else os.path.join(rd, m)

    def unfinished(self):
        d = os.path.join(self.folder(), "zim") if self.folder() else ""
        try:
            names = os.listdir(d) if d else []
        except OSError:
            return []
        done = {f.lower() for f in names if f.lower().endswith(".zim")}
        return sorted(f[:-9] for f in names if f.lower().endswith(".zim.part") and f[:-5].lower() not in done)

    # ---------- reading a .zim
    def _arch(self, path):
        with self.lock:
            got = self.open.get(path)
            if got:
                got[2] = time.time()
                return got[0], got[1]
            from libzim.reader import Archive
            a = Archive(path)
            if len(self.open) >= 220:         # an open file costs little: keep them all open
                old = min(self.open, key=lambda k: self.open[k][2])
                del self.open[old]
            self.open[path] = [a, threading.Lock(), time.time()]
            return a, self.open[path][1]

    def have_libzim(self):
        try:
            import libzim.reader  # noqa: F401
            return True
        except ImportError:
            return False

    def _meta_zim(self, path, stem, size):
        a, _ = self._arch(path)              # opening it now also makes the first search faster
        m = {"size": size, "articles": 0, "title": "", "desc": "", "lang": "", "icon": False, "creator": "", "main": ""}
        try:
            m["articles"] = int(a.article_count)
        except Exception:      # noqa: BLE001
            pass
        for k, field in (("Title", "title"), ("Description", "desc"), ("Language", "lang"), ("Creator", "creator"),
                         ("LongDescription", "long")):
            try:
                m[field] = bytes(a.get_metadata(k)).decode("utf-8", "replace").strip()
            except Exception:      # noqa: BLE001
                pass
        try:
            m["main"] = a.main_entry.get_item().path if a.has_main_entry else ""
        except Exception:      # noqa: BLE001
            pass
        try:
            m["fulltext"] = bool(a.has_fulltext_index)
        except Exception:      # noqa: BLE001
            m["fulltext"] = False
        try:
            if a.has_illustration(48):
                os.makedirs(self.icon_dir, exist_ok=True)
                with open(os.path.join(self.icon_dir, stem + ".png"), "wb") as f:
                    f.write(bytes(a.get_illustration_item(48).content))
                m["icon"] = True
        except Exception:      # noqa: BLE001
            pass
        return m

    def _meta_rachel(self, m, root):
        info = {"size": 0, "articles": 0, "title": "", "desc": "", "lang": "en", "icon": False, "main": ""}
        frag = ""
        for name in ("rachel-index.php", "index.htmlf"):
            try:
                with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
                    frag = f.read(60000)
                break
            except OSError:
                continue
        if frag:
            img = re.search(r"(?is)<img[^>]+src=\"<\?php echo \$dir \?>/([^\"]+)\"", frag)
            if img and os.path.isfile(os.path.join(root, img.group(1))):
                info["icon"] = "r/" + img.group(1)
            frag = re.sub(r"(?s)<\?php.*?\?>", "", frag)          # the PHP bits hold ">" that would cut tags short
            t = re.search(r"(?is)<h2[^>]*>(.*?)</h2>", frag)
            info["title"] = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", t.group(1))).split()) if t else ""
            p = re.search(r"(?is)<p[^>]*>(.*?)</p>", frag)
            info["desc"] = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", p.group(1))).split())[:400] if p else ""
        for cand in ("logo.png", "logo.jpg"):
            if not info["icon"] and os.path.isfile(os.path.join(root, cand)):
                info["icon"] = "r/" + cand
        info["main"] = "index.html" if os.path.isfile(os.path.join(root, "index.html")) else ""
        return info

    def _scan_meta(self):
        """Background: read the details of packs we haven't seen (or that changed), then index RACHEL titles."""
        try:
            changed = False
            for pid, kind, stem, path, size, mtime in self._files():
                old = self.meta.get(pid)
                if kind == "zim":
                    if old and old.get("size") == size:
                        continue
                    try:
                        self.meta[pid] = self._meta_zim(path, stem, size)
                    except Exception as e:      # noqa: BLE001 - a broken or half-copied file
                        self.meta[pid] = {"size": size, "error": str(e)[:200]}
                    changed = True
                else:
                    if old and old.get("done") == mtime and old.get("v") == 2:
                        continue
                    info = self._meta_rachel(stem, path)
                    info["done"], info["v"] = mtime, 2
                    if old and old.get("done") == mtime:          # keep the size and page count worked out before
                        info["size"], info["articles"] = old.get("size", 0), old.get("articles", 0)
                    self.meta[pid] = info
                    changed = True
                if changed:
                    with self.lock:
                        self._cat = (0, None)
                    self._save("vault-meta.json", self.meta)
                    changed = False
            for pid, kind, stem, path, size, mtime in self._files():
                if kind == "rachel":
                    self._rachel_index(stem, path, mtime)
        except Exception as e:      # noqa: BLE001
            self.log("vault scan:", e)

    def _rachel_index(self, m, root, done):
        """Titles of every page in a RACHEL module (built once, kept in Archie's data folder)."""
        if m in self.rindex:
            return self.rindex[m]
        cache = self._load("vault-r-%s.json" % m, None)
        if cache and cache.get("done") == done:
            self.rindex[m] = cache["pages"]
            info = self.meta.get("r:" + m) or {}
            if not info.get("size") and cache.get("size"):
                info["size"], info["articles"] = cache["size"], len(cache["pages"])
                self.meta["r:" + m] = info
                self._save("vault-meta.json", self.meta)
            return cache["pages"]
        pages, total = [], 0
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith((".", "_")) and d not in ("search", "admin")]
            for f in fn:
                low = f.lower()
                p = os.path.join(dp, f)
                try:
                    total += os.path.getsize(p)
                except OSError:
                    pass
                if len(pages) >= 120000:
                    continue
                rel = os.path.relpath(p, root).replace("\\", "/")
                if low.endswith((".html", ".htm")):
                    try:
                        with open(p, "rb") as fh:
                            head = fh.read(4096).decode("utf-8", "replace")
                    except OSError:
                        continue
                    t = re.search(r"(?is)<title[^>]*>(.*?)</title>", head)
                    title = " ".join(htmllib.unescape(t.group(1)).split()) if t else ""
                    if not title:
                        h = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", head)
                        title = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", h.group(1))).split()) if h else ""
                    pages.append([rel, title or os.path.splitext(f)[0].replace("_", " ")])
                elif low.endswith(".pdf"):
                    pages.append([rel, os.path.splitext(f)[0].replace("_", " ") + " (PDF)"])
        self.rindex[m] = pages
        self._save("vault-r-%s.json" % m, {"done": done, "pages": pages, "size": total})
        info = self.meta.get("r:" + m) or {}
        info["size"], info["articles"] = total, len(pages)
        self.meta["r:" + m] = info
        self._save("vault-meta.json", self.meta)
        with self.lock:
            self._cat = (0, None)
        return pages

    def start_scan(self):
        if self._scan and self._scan.is_alive():
            return
        self._scan = threading.Thread(target=self._scan_meta, daemon=True, name="vault-scan")
        self._scan.start()

    # ---------- the catalogue
    def packs(self):
        """{id: pack} for the newest copy of each pack, with older copies and smaller variants noted."""
        with self.lock:
            if self._cat[1] is not None and time.time() - self._cat[0] < 60:
                return self._cat[1]
        files = self._files()
        bykey = {}
        for pid, kind, stem, path, size, mtime in files:
            k = key_of(stem) if kind == "zim" else stem
            bykey.setdefault(k, []).append((date_of(stem), pid, kind, stem, path, size, mtime))
        packs = {}
        for k, copies in bykey.items():
            copies.sort(reverse=True)
            _, pid, kind, stem, path, size, mtime = copies[0]
            m = self.meta.get(pid) or {}
            row = self.csv.get(k) or {}
            if row.get("shelf") in SHELF_NAME:
                shelf = row["shelf"]
            else:
                shelf = LETTER_SHELF.get(row.get("pack", ""), "other")
                if row.get("pack") == "H" or not row:
                    shelf = next((s for pre, s in BIG_SHELF if k.startswith(pre)), shelf)
            title = row.get("title") or m.get("title") or stem
            packs[pid] = {
                "id": pid, "kind": kind, "name": stem, "key": k, "family": family_of(k) if kind == "zim" else k,
                "title": title, "zim_title": m.get("title", ""), "desc": m.get("desc", ""), "shelf": shelf,
                "ages": ages_of(k, shelf), "tags": tags_of(k, title), "bytes": m.get("size") or size, "size": gb(m.get("size") or size),
                "date": date_of(stem), "articles": m.get("articles", 0), "icon": bool(m.get("icon")), "lang": m.get("lang", ""),
                "fulltext": bool(m.get("fulltext")) if kind == "zim" else True, "error": m.get("error", ""), "scanned": bool(m),
                "pocket": row.get("pocket") == "1", "older": [{"name": c[3], "size": gb(c[5]), "date": c[0]} for c in copies[1:]],
                "subset": kind == "zim" and k.startswith("wikipedia_en_") and not k.startswith(("wikipedia_en_all", "wikipedia_en-simple")),
                "license": row.get("license", ""), "verdict": row.get("verdict", ""), "credit": row.get("credit", ""),
                "license_url": row.get("license_url", ""),
            }
        fams = {}
        for p in packs.values():
            fams.setdefault(p["family"], []).append(p)
        for fam in fams.values():
            fam.sort(key=lambda p: -p["bytes"])
            for p in fam[1:]:
                p["variant_of"] = fam[0]["id"]
            fam[0]["variants"] = [{"id": p["id"], "title": p["title"], "size": p["size"]} for p in fam[1:]]
        with self.lock:
            self._cat = (time.time(), packs)
        return packs

    def _marks(self, packs):
        seen = self._load("vault-seen.json", None)
        if seen is None:      # the first time: everything already there counts as seen
            seen = {p["key"]: p["name"] for p in packs.values()}
            self._save("vault-seen.json", seen)
        for p in packs.values():
            p["mark"] = "" if seen.get(p["key"]) == p["name"] else ("updated" if p["key"] in seen else "new")

    def catalog(self, ages=""):
        if not self.have_libzim():
            return {"error": "The Vault needs one extra piece to read .zim files: run 'pip install libzim', then start Vault Search again (Vault Search.exe already includes it)."}
        self.start_scan()
        packs = self.packs()
        self._marks(packs)
        shelves = []
        for sid, title, desc in SHELVES:
            lst = [p for p in packs.values() if p["shelf"] == sid and not p.get("variant_of") and (not ages or ages in p["ages"])]
            lst.sort(key=lambda p: (p.get("subset", False), -math.log10(max(p["bytes"], 1)) if sid != "code" else p["title"].lower()))
            if lst:
                shelves.append({"id": sid, "title": title, "desc": desc, "packs": [self._card(p) for p in lst]})
        visible = [p for p in packs.values() if not p.get("variant_of")]
        pending = sum(1 for p in packs.values() if not p["scanned"])
        return {"folder": self.folder(), "shelves": shelves, "packs": len(visible), "bytes": sum(p["bytes"] for p in packs.values()),
                "size": gb(sum(p["bytes"] for p in packs.values())), "scanning": pending,
                "indexing": bool(self._scan and self._scan.is_alive()), "unfinished": self.unfinished(),
                "updated": [self._card(p) for p in visible if p["mark"]], "saved": self.saved()[:12],
                "port": self.content_port, "csv": bool(self.csv), "cards": bool(self.study_dir)}

    @staticmethod
    def _card(p):
        return {k: p.get(k) for k in ("id", "kind", "title", "desc", "shelf", "ages", "size", "articles", "icon", "mark", "date",
                                      "variants", "older", "error", "subset", "scanned", "license", "verdict")}

    def pack(self, pid):
        packs = self.packs()
        self._marks(packs)
        p = packs.get(pid)
        if not p:
            return {"error": "That pack isn't in the vault any more."}
        out = dict(p)
        out["shelf_title"] = SHELF_NAME.get(p["shelf"], "")
        out["front"] = self.front_url(pid)
        out["long"] = (self.meta.get(pid) or {}).get("long", "")
        mine = set(p["tags"])
        rel = []
        for q in packs.values():
            if q["id"] == pid or q.get("variant_of") or q["family"] == p["family"]:
                continue
            score = 2 * len(mine & set(q["tags"])) + (1 if q["shelf"] == p["shelf"] else 0)
            if score >= 2:
                rel.append((score, q["bytes"], q))
        rel.sort(key=lambda x: (-x[0], -x[1]))
        out["related"] = [self._card(q) for _, _, q in rel[:8]]
        return out

    def mark_seen(self, pid=None):
        packs = self.packs()
        seen = self._load("vault-seen.json", {}) or {}
        for p in packs.values():
            if pid is None or p["id"] == pid:
                seen[p["key"]] = p["name"]
        self._save("vault-seen.json", seen)
        return {"ok": True}

    def icon(self, pid):
        """(bytes, mime) of a pack's icon, or None."""
        m = self.meta.get(pid) or {}
        if pid.startswith("r:") and isinstance(m.get("icon"), str):
            p = os.path.join(self._rroot(pid[2:]), m["icon"][2:])
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    return f.read(), mimetypes.guess_type(p)[0] or "image/png"
            return None
        p = os.path.join(self.icon_dir, pid + ".png")
        if m.get("icon") and os.path.isfile(p):
            with open(p, "rb") as f:
                return f.read(), "image/png"
        return None

    # ---------- addresses of pages (served by the content server)
    def base_url(self):
        return "http://127.0.0.1:%d" % self.content_port

    def front_url(self, pid):
        if pid.startswith("r:"):
            return "%s/r/%s/" % (self.base_url(), urllib.parse.quote(pid[2:]))
        return "%s/z/%s/" % (self.base_url(), urllib.parse.quote(pid))

    def page_url(self, pid, path):
        q = urllib.parse.quote(path, safe="/")
        if pid.startswith("r:"):
            return "%s/r/%s/%s" % (self.base_url(), urllib.parse.quote(pid[2:]), q)
        return "%s/z/%s/%s" % (self.base_url(), urllib.parse.quote(pid), q)

    def _zpath(self, pid):
        p = self.packs().get(pid)
        if p and p["kind"] == "zim":
            for fid, kind, stem, path, size, mtime in self._files():
                if fid == pid:
                    return path
        return ""

    # ---------- search
    def _scope(self, scope, ages=""):
        packs = [p for p in self.packs().values() if not p.get("error")]
        if scope.startswith("pack:"):
            return [p for p in packs if p["id"] == scope[5:]]
        lst = [p for p in packs if not p.get("variant_of") and not p.get("subset")]
        if scope.startswith("shelf:"):
            lst = [p for p in lst if p["shelf"] == scope[6:]]
        if ages:
            lst = [p for p in lst if ages in p["ages"]]
        return lst

    def _topic_zim(self, p, a_info):
        """The main article for the question's own subject ("how to treat a burn" -> Burn), found by exact title. No search index needed."""
        a, lk = self._arch(self._zpath(p["id"]))
        subject = a_info["subject"]
        roman = {"1": "I", "2": "II", "3": "III", "one": "I", "two": "II"}
        cands = []
        ph = a_info["phrase"]
        if ph and len(ph.split()) > 1:      # the whole question, minus "how to" / "what is": "Causes of World War I"
            parts = ph.split()
            for v in (ph, " ".join(roman.get(w, w) for w in parts)):
                cands.append((v, len(subject) + 1, True))
        for size in (3, 2, 1):
            for i in range(0, len(subject) - size + 1):
                cands.append((" ".join(subject[i:i + size]), size, False))
        out, seen, covered = [], set(), set()
        for g, size, whole in cands[:12]:
            gw = set(g.lower().split())
            if size == 1 and a_info["code"] and len(subject) > 1:      # "godot move character": not the article on Move
                continue
            if not whole and gw <= covered:        # "Bicycle chain" already found: skip "Bicycle" and "Chain"
                continue
            found = False
            for cand in dict.fromkeys([g[:1].upper() + g[1:], smart_title(g), g.title(), stem(g)[:1].upper() + stem(g)[1:], g]):
                for path in (cand.replace(" ", "_"), "A/" + cand.replace(" ", "_")):
                    try:
                        e = a.get_entry_by_path(path)
                    except (KeyError, RuntimeError):
                        continue
                    try:
                        moved = False
                        for _ in range(4):
                            if not e.is_redirect:
                                break
                            e = e.get_redirect_entry()
                            moved = True
                        # one word that redirects somewhere else ("dead" -> Death) is a different subject; a phrase that does
                        # ("high blood pressure" -> Hypertension) is a synonym. Packs in other languages must match exactly.
                        if moved and (size == 1 or not p["key"].startswith(("wikipedia_en", "mdwiki", "wikem"))) and \
                                stem(g.lower())[:5] not in (e.title or "").lower():
                            break
                        if e.path in seen:
                            found = True
                            break
                        item = e.get_item()
                        if not item.mimetype.startswith("text/html"):
                            break
                        head = bytes(item.content)[:6000].decode("utf-8", "replace").lower()
                        if "may refer to" in head or "(disambiguation)" in (e.title or "").lower():
                            break
                        seen.add(e.path)
                        out.append((e.path, e.title, size, whole))
                        covered |= gw
                        found = True
                    except Exception:      # noqa: BLE001
                        pass
                    break
                if found:
                    break
            if len(out) >= 3:
                break
        return out, len(out)

    def _titles_zim(self, p, q, n):
        a, lk = self._arch(self._zpath(p["id"]))
        from libzim.suggestion import SuggestionSearcher
        with lk:
            s = SuggestionSearcher(a).suggest(q)
            total = s.getEstimatedMatches()
            paths = list(s.getResults(0, n))
        out = []
        for path in paths:
            try:
                e = a.get_entry_by_path(path)
                out.append((path, e.title))
            except Exception:      # noqa: BLE001
                continue
        return out, total

    def _text_zim(self, p, q, n):
        a, lk = self._arch(self._zpath(p["id"]))
        if not a.has_fulltext_index:
            return [], 0
        from libzim.search import Query, Searcher
        with lk:
            s = Searcher(a).search(Query().set_query(q))
            total = s.getEstimatedMatches()
            paths = list(s.getResults(0, n))
        out = []
        for path in paths:
            try:
                out.append((path, a.get_entry_by_path(path).title))
            except Exception:      # noqa: BLE001
                continue
        return out, total

    def _titles_rachel(self, p, q, n):
        m = p["id"][2:]
        pages = self.rindex.get(m)
        if pages is None:
            cache = self._load("vault-r-%s.json" % m, None)
            pages = cache["pages"] if cache else []
            if cache:
                self.rindex[m] = pages
        words = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1]
        if not words:
            return [], 0
        need = [stem(w)[:6] for w in words]
        hits = []
        for path, title in pages:
            t = title.lower()
            got = sum(1 for w in need if w in t)
            if got == len(need) or (len(need) > 2 and got >= len(need) - 1):
                hits.append((-got, 0 if t.startswith(words[0]) else 1, len(t), path, title))
        hits.sort()
        hits = [(a2, b2, c2, d2, e2) for a2, b2, c2, d2, e2 in hits]
        return [(h[3], h[4]) for h in hits[:n]], len(hits)

    def search(self, q, scope="all", mode="title", ages="", n=40, lang="", debug=False):
        """{results: [{id, pack, title, path, url, snippet}], packs: [{id, title, count}], skipped: [...]}."""
        q = " ".join((q or "").split())[:200]
        if not q:
            return {"results": [], "packs": []}
        if not self.have_libzim():
            return {"error": "The Vault needs Install Extras.bat (the .zim reader) first."}
        lst = self._scope(scope, ages)
        one = scope.startswith("pack:")
        now = time.time()
        A = analyze(q)
        if not one:
            lst = [p for p in lst if self.slow.get(p["id"], 0) < now]
            if scope == "all" and not A["code"]:      # programming Q&A and docs only answer programming questions
                lst = [p for p in lst if p["shelf"] != "code"]
            elif scope == "all":                       # and programming questions don't need the farming or health shelves
                lst = [p for p in lst if p["shelf"] in ("code", "repair", "core") or p["key"].startswith(("wikiversity", "jeffe", "opendatastructures"))]
        qq = A["clean"]
        per = 30 if one else (6 if mode == "title" else 5)
        deadline = 25.0 if one else (8.0 if mode == "title" else 20.0)
        jobs = {}
        took = {}

        def timed(fn, p, *a):
            t0 = time.time()
            try:
                return fn(p, *a)
            finally:
                took[p["id"]] = round(time.time() - t0, 2)
        lst.sort(key=lambda p: (not p["key"].startswith(("wikipedia_en_all", "stackoverflow")), p["bytes"]))   # small packs answer fast
        topic = {}
        if mode == "title":
            for p in lst:
                if p["kind"] == "zim" and (p["key"].startswith(TOPIC_PACKS) or (A["define"] and p["key"].startswith("wiktionary_en"))):
                    topic[self.pool.submit(self._topic_zim, p, A)] = p
        for p in lst:
            if p["kind"] == "rachel":
                if mode == "title":
                    jobs[self.pool.submit(timed, self._titles_rachel, p, " ".join(A["content"]), per)] = p
            elif mode == "title" or p.get("fulltext"):
                if mode == "title":      # titles: the subject ("bowline knot"); pages: the whole question
                    jobs[self.pool.submit(timed, self._titles_zim, p, " ".join(A["subject"]), per)] = p
                else:
                    jobs[self.pool.submit(timed, self._text_zim, p, qq, per)] = p
        done, late = wait(jobs, timeout=deadline)
        key_late = [f for f in late if jobs[f]["key"].startswith(("wikipedia_en_all", "wikipedia_en-simple", "mdwiki"))]
        if key_late:      # the main encyclopedias are worth a few more seconds
            wait(key_late, timeout=6.0)
        for f in list(late):     # anything that finished meanwhile counts
            if f.done():
                late.discard(f)
                done.add(f)
        tdone, _ = wait(topic, timeout=6.0)
        skipped, unreached = [], 0
        for f in late:
            if f.cancel():          # never started: there wasn't time, it isn't slow
                unreached += 1
                continue
            self.slow[jobs[f]["id"]] = now + 600
            skipped.append(jobs[f]["title"])
        words = [w for w in A["content"] if len(w) > 2] or [q.lower()]
        scored, counts = [], []
        for f in tdone:
            p = topic[f]
            try:
                hits, _ = f.result()
            except Exception:      # noqa: BLE001
                continue
            n_subj = max(1, len(A["subject"]))
            pr = prior_of(p["key"])
            if p["key"].startswith("wikivoyage"):
                pr = 0.7
            if p["key"].startswith("vikidia") and not A["kids"]:
                pr = 0.85
            if lang_of(p["key"]) not in ("en", "mul", LANG3.get(lang, lang)):
                pr *= 0.6
            for path, title, size, whole in hits:
                frac = 1.0 if whole else min(1.0, size / n_subj)
                s = pr * (1.0 + 2.6 * frac ** 1.5)
                if A["howto"] and not whole:
                    s *= 0.8
                if A["story"] and not p["key"].startswith(STORY_PACKS):
                    s *= 0.6
                if A["kids"] and "kids" in p["ages"]:
                    s += 0.6
                scored.append((s, p, path, title))
        for f in done:
            p = jobs[f]
            try:
                hits, total = f.result()
            except Exception:      # noqa: BLE001
                continue
            if not hits:
                continue
            counts.append({"id": p["id"], "title": p["title"], "count": int(total or len(hits)), "shelf": p["shelf"]})
            weight = prior_of(p["key"])
            if A["define"] and p["key"].startswith(("wiktionary_en_", "wiktionary_en-simple")):
                weight = 1.3
            if A["kids"] and "kids" in p["ages"]:
                weight *= 1.35
            if A["story"] and p["key"].startswith(STORY_PACKS):
                weight *= 1.8
            if lang_of(p["key"]) not in ("en", "mul", LANG3.get(lang, lang)):
                weight *= 0.6
            practical = A["howto"] and p["key"].startswith(PRACTICAL) or (A["howto"] and any(x in p["key"] for x in PRACTICAL))
            if lang and lang in (p.get("lang") or "").lower().split(","):      # packs in the reader's language come first
                weight *= 1.8
            for rank, (path, title) in enumerate(hits):
                t = (title or "").lower()
                if VULGAR.search(t) and not VULGAR.search(q):
                    continue
                if "(disambiguation)" in t:
                    continue
                cov = coverage(t, A["content"])
                head = re.split(r" [-|] ", t)[0]          # "Treating Burns - A Community Guide..." -> "treating burns"
                n_words = max(1, len(head.split()))
                s = weight * (1.0 / (1 + 0.3 * rank) + 1.3 * cov * min(1.0, 6.0 / n_words))
                pairs = sum(1 for a2, b2 in zip(A["words"], A["words"][1:])
                            if not (a2 in STOPWORDS and b2 in STOPWORDS) and (stem(a2)[:5] + " " + stem(b2)[:4]) in " ".join(stem(x) for x in t.split()))
                s += weight * min(1.0, 0.5 * pairs)      # the question's own phrases ("won't charge", "plant maize") in the title
                if cov == 0:
                    s -= 0.6
                elif cov >= 0.99 and practical:      # a how-to question answered by a how-to source (guides more than Q&A)
                    s += (0.3 if ("stackexchange" in p["key"] or "superuser" in p["key"] or "askubuntu" in p["key"]) else 0.8) * weight
                if t == qq.lower() or t == q.lower():
                    s += 1.5
                if BAD_TITLE.search(title or "") or SE_JUNK.search(title or "") or "/tagged/" in path or path.startswith("users/"):
                    s -= 1.5
                scored.append((s, p, path, title))
        scored.sort(key=lambda x: -x[0])
        seen_titles, unique = set(), []       # the same article from two Wikipedia editions shows once (the best one)
        for x in scored:
            fam = "wikipedia" if x[1]["key"].startswith(("wikipedia_", "mdwiki")) else x[1]["id"]
            k = (fam, " ".join((x[3] or x[2]).lower().split()))
            if k not in seen_titles:
                seen_titles.add(k)
                unique.append(x)
        scored = unique
        if not one:     # don't let one pack fill the page
            out, per_pack = [], {}
            for x in scored:
                k = x[1]["id"]
                if per_pack.get(k, 0) < 4:
                    out.append(x)
                    per_pack[k] = per_pack.get(k, 0) + 1
            scored = out
        scored = scored[:n]
        snips = {}
        sj = {self.pool.submit(self._snippet, p, path, words): i for i, (s, p, path, title) in enumerate(scored[:24])}
        d2, _ = wait(sj, timeout=6.0)
        for f in d2:
            try:
                snips[sj[f]] = f.result()
            except Exception:      # noqa: BLE001
                pass
        results = [{"id": p["id"], "pack": p["title"], "title": title or path, "path": path, "url": self.page_url(p["id"], path),
                    "snippet": snips.get(i, ""), "score": round(s, 3)} for i, (s, p, path, title) in enumerate(scored)]
        counts.sort(key=lambda c: -c["count"])
        out = {"q": q, "mode": mode, "results": results, "packs": counts, "skipped": skipped, "unreached": unreached, "searched": len(jobs)}
        if debug:
            out["timing"] = took
            out["scores"] = [round(x[0], 3) for x in scored]
        return out

    def _read_page(self, pid, path, limit=400000):
        """(title, html text) of one page."""
        if pid.startswith("r:"):
            root = self._rroot(pid[2:])
            fp = os.path.normpath(os.path.join(root, path))
            if not fp.startswith(os.path.normpath(root)) or not fp.lower().endswith((".html", ".htm")):
                return "", ""
            with open(fp, "rb") as f:
                h = f.read(limit).decode("utf-8", "replace")
            t = re.search(r"(?is)<title[^>]*>(.*?)</title>", h)
            return (htmllib.unescape(t.group(1)).strip() if t else ""), h
        a, lk = self._arch(self._zpath(pid))
        e = a.get_entry_by_path(path)
        for _ in range(5):
            if not e.is_redirect:
                break
            e = e.get_redirect_entry()
        item = e.get_item()
        if not item.mimetype.startswith("text/html"):
            return e.title, ""
        return e.title, bytes(item.content)[:limit].decode("utf-8", "replace")

    def _snippet(self, p, path, words):
        title, h = self._read_page(p["id"], path, 160000)
        if not h:
            return ""
        if "js-post-body" in h:      # a Stack Exchange page: start at the question itself, not the site's menus
            m = re.search(r'(?is)<div[^>]+class="[^"]*js-post-body[^"]*"[^>]*>(.*?)</div>\s*(?:<div|</div>)', h)
            if m:
                return snippet(text_of_html(m.group(1)), words)
        return snippet(text_of_html(h), words)

    # ---------- random and today
    def _random_from(self, p, tries=30, min_bytes=None):
        if min_bytes is None:
            min_bytes = 1200 if _has(p["key"], KIDS_ONLY) else 3000
        if p["kind"] == "rachel":
            pages = [x for x in (self.rindex.get(p["id"][2:]) or []) if not x[0].lower().endswith(".pdf")]
            if not pages:
                return None
            path, title = random.choice(pages)
            return {"id": p["id"], "pack": p["title"], "path": path, "title": title, "url": self.page_url(p["id"], path)}
        a, lk = self._arch(self._zpath(p["id"]))
        try:
            main = a.main_entry.get_item().path if a.has_main_entry else ""
            n = a.entry_count
        except Exception:      # noqa: BLE001
            main, n = "", 0
        for i in range(tries):
            try:     # libzim's own random pick, mixed with picks by position (some packs make the first one repeat)
                e = a._get_entry_by_id(random.randrange(n)) if (i % 2 and n) else a.get_random_entry()
                if e.is_redirect or e.path == main:
                    continue
                item = e.get_item()
                if not item.mimetype.startswith("text/html") or item.size < min_bytes or BAD_TITLE.search(e.title or ""):
                    continue
                if re.search(r"(?i)disambiguation|^\d{1,4}$", e.title or ""):
                    continue
                return {"id": p["id"], "pack": p["title"], "path": e.path, "title": e.title, "url": self.page_url(p["id"], e.path)}
            except Exception:      # noqa: BLE001
                continue
        return None

    def random_page(self, scope="all", ages=""):
        lst = [p for p in self._scope(scope, ages) if not p["key"].startswith(NOT_READING) and (p["kind"] == "zim" or self.rindex.get(p["id"][2:]))]
        if not lst:
            return {"error": "No packs to pick from here yet."}
        weights = [math.sqrt(max(p["articles"], 1)) for p in lst]
        for _ in range(6):
            p = random.choices(lst, weights)[0]
            got = self._random_from(p)
            if got:
                return got
        return {"error": "Couldn't find a good page just now. Try again."}

    def today(self):
        """Three pages picked for today (kids, teens, adults); the same all day."""
        day = datetime.date.today().isoformat()
        saved = self._load("vault-today.json", {})
        if saved.get("date") == day and saved.get("picks"):
            return {"date": day, "picks": saved["picks"]}
        packs = [p for p in self.packs().values() if not p.get("error")]
        picks = []
        used = set()
        for who in ("kids", "teens", "adults"):
            cands = []
            for pre in TODAY_FROM[who]:
                cands += [p for p in packs if p["key"].startswith(pre) and p["id"] not in used and not p.get("variant_of")]
            if not cands:
                cands = [p for p in packs if who in p["ages"] and not p.get("variant_of") and not p["key"].startswith(NOT_READING)]
            random.Random(day + who).shuffle(cands)
            for p in cands[:4]:
                got = self._random_from(p, tries=60, min_bytes=6000 if who != "kids" else 1200)
                if got:
                    got["for"] = who
                    got["snippet"] = self._snippet(p, got["path"], [])
                    picks.append(got)
                    used.add(p["id"])
                    break
        if picks:
            self._save("vault-today.json", {"date": day, "picks": picks})
        return {"date": day, "picks": picks}

    # ---------- saved pages and Study
    def saved(self):
        return self._load("vault-saved.json", [])

    def save_page(self, b):
        pid, path = b.get("id", ""), b.get("path", "")
        packs = self.packs()
        if pid not in packs or not path:
            return {"error": "That page isn't in the vault."}
        lst = [s for s in self.saved() if not (s["id"] == pid and s["path"] == path)]
        lst.insert(0, {"id": pid, "path": path, "title": (b.get("title") or path)[:200], "pack": packs[pid]["title"],
                       "url": self.page_url(pid, path), "at": datetime.date.today().isoformat()})
        self._save("vault-saved.json", lst[:500])
        return {"ok": True, "saved": lst[:12]}

    def unsave(self, b):
        lst = [s for s in self.saved() if not (s["id"] == b.get("id") and s["path"] == b.get("path"))]
        self._save("vault-saved.json", lst)
        return {"ok": True, "saved": lst[:12]}

    def cards(self, b):
        """Flashcards from a page into a Study deck (Archie's main model writes them)."""
        pid, path = b.get("id", ""), b.get("path", "")
        if pid not in self.packs() or not path:
            return {"error": "That page isn't in the vault."}
        if not self.study_dir:
            return {"error": "Study isn't set up."}
        title, h = self._read_page(pid, path, 600000)
        text = text_of_html(h)
        if len(text) < 300:
            return {"error": "There isn't enough text on this page to make cards from."}
        import archie_study
        from archie_brain import quick_chat
        deck = " ".join((b.get("deck") or "").split())[:60] or ("Vault - " + re.sub(r"\s*\(.*", "", self.packs()[pid]["title"]))
        cards = archie_study.make_cards(quick_chat, self.get_model(), text[:24000], title or b.get("title") or "this page", n=int(b.get("n") or 8))
        if not cards:
            return {"error": "Archie couldn't make cards from this page. Is Ollama running?"}
        archie_study.Study(self.study_dir).add_cards(deck, cards, source="Vault: %s (%s)" % (title or path, self.packs()[pid]["title"]))
        return {"ok": True, "deck": deck, "count": len(cards), "cards": cards[:3]}

    # ---------- the API the Vault page calls
    def get(self, what, a):
        if what == "catalog":
            return self.catalog(a("ages", ""))
        if what == "pack":
            return self.pack(a("id"))
        if what == "search":
            return self.search(a("q", ""), a("scope", "all") or "all", a("mode", "title"), a("ages", ""), lang=a("lang", "").lower()[:3])
        if what == "random":
            return self.random_page(a("scope", "all") or "all", a("ages", ""))
        if what == "today":
            return self.today()
        if what == "saved":
            return {"saved": self.saved()}
        return {"error": "unknown"}

    def post(self, what, b):
        if what == "save":
            return self.save_page(b)
        if what == "unsave":
            return self.unsave(b)
        if what == "seen":
            return self.mark_seen(b.get("id"))
        if what == "cards":
            return self.cards(b)
        if what == "rescan":
            with self.lock:
                self._cat = (0, None)
            self.start_scan()
            return {"ok": True}
        return {"error": "unknown"}

    # ---------- the content server (pages, on their own port)
    def start_content(self, port=8766):
        for p in range(port, port + 10):
            try:
                self.server = _content_server(self, p)
            except OSError:
                continue
            self.content_port = p
            threading.Thread(target=self.server.serve_forever, daemon=True, name="vault-http").start()
            return p
        return 0

    def stop(self):
        if self.server:
            self.server.shutdown()


def _rachel_front(m, title, frag):
    base = "/r/" + urllib.parse.quote(m)
    frag = frag.replace("<?php echo $dir ?>", base).replace("<?php echo $moddir ?>", m)
    frag = re.sub(r"(?s)<\?php.*?\?>", "", frag)
    frag = re.sub(r"(?is)<form\b.*?</form>", "", frag)      # their search needs PHP: the Vault's own search covers it
    return ("<!doctype html><html><head><meta charset='utf-8'><title>%s</title><style>body{font-family:system-ui,sans-serif;"
            "max-width:900px;margin:30px auto;padding:0 20px;line-height:1.55;color:#1d1f1a}img{max-width:220px}"
            "ul{columns:2}ul.triple{columns:3}li{margin:3px 0}a{color:#2c5f9e}h2 a{color:inherit;text-decoration:none}</style>"
            "</head><body>%s</body></html>") % (htmllib.escape(title), frag)


def _content_server(vault, port):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _head(self, code, ctype, n, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(n))
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
                             "connect-src 'self' data: blob:; form-action 'none'; frame-ancestors http://127.0.0.1:* http://localhost:*")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()

        def _bytes(self, code, body, ctype, cache="max-age=3600"):
            rng = self.headers.get("Range")
            total = len(body)
            m = re.match(r"bytes=(\d*)-(\d*)$", rng or "")
            if m and total and (m.group(1) or m.group(2)):
                a = int(m.group(1)) if m.group(1) else max(0, total - int(m.group(2)))
                b = int(m.group(2)) if m.group(1) and m.group(2) else total - 1
                b = min(b, total - 1)
                if a > b:
                    self._head(416, ctype, 0, {"Content-Range": "bytes */%d" % total})
                    return
                self._head(206, ctype, b - a + 1, {"Content-Range": "bytes %d-%d/%d" % (a, b, total), "Accept-Ranges": "bytes",
                                                    "Cache-Control": cache})
                self._write(body[a:b + 1])
                return
            self._head(code, ctype, total, {"Accept-Ranges": "bytes", "Cache-Control": cache})
            self._write(body)

        def _write(self, data):
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _file(self, p):
            ctype = EXTRA_MIME.get(os.path.splitext(p)[1].lower()) or mimetypes.guess_type(p)[0] or "application/octet-stream"
            size = os.path.getsize(p)
            if ctype.startswith("text/html"):
                with open(p, "rb") as f:
                    return self._bytes(200, _inject(f.read()), "text/html; charset=utf-8")
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8" if "charset" not in ctype else ""
            rng = self.headers.get("Range")
            m = re.match(r"bytes=(\d*)-(\d*)$", rng or "")
            a, b, code = 0, size - 1, 200
            if m and size and (m.group(1) or m.group(2)):
                a = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
                b = min(int(m.group(2)), size - 1) if m.group(1) and m.group(2) else size - 1
                code = 206
            extra = {"Accept-Ranges": "bytes", "Cache-Control": "max-age=3600"}
            if code == 206:
                extra["Content-Range"] = "bytes %d-%d/%d" % (a, b, size)
            self._head(code, ctype, b - a + 1, extra)
            with open(p, "rb") as f:
                f.seek(a)
                left = b - a + 1
                while left > 0:
                    chunk = f.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        return
                    left -= len(chunk)

        def _missing(self, why="That page isn't in this pack."):
            body = ("<!doctype html><meta charset=utf-8><body style='font-family:system-ui;padding:40px;color:#333'>"
                    "<h2>Not here</h2><p>%s</p><p><a href='javascript:history.back()'>Go back</a></p>" % htmllib.escape(why)).encode()
            self._bytes(404, _inject(body), "text/html; charset=utf-8", "no-cache")

        def do_GET(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                return self._missing("Wrong address.")
            path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            try:
                if path.startswith("/z/"):
                    return self._zim(path[3:])
                if path.startswith("/r/"):
                    return self._rachel(path[3:])
            except Exception as e:      # noqa: BLE001
                return self._missing("Couldn't open it (%s)." % e)
            return self._missing("Unknown address.")

        def _redirect(self, url):
            self.send_response(302)
            self.send_header("Location", url)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _zim(self, rest):
            pid, _, p = rest.partition("/")
            zp = vault._zpath(pid)
            if not zp:
                return self._missing("That pack isn't in the vault.")
            a, lk = vault._arch(zp)
            if not p:
                if not a.has_main_entry:
                    return self._missing("This pack has no front page. Use the search box above.")
                e = a.main_entry
                for _ in range(5):
                    if not e.is_redirect:
                        break
                    e = e.get_redirect_entry()
                return self._redirect("/z/%s/%s" % (urllib.parse.quote(pid), urllib.parse.quote(e.path, safe="/")))
            try:
                e = a.get_entry_by_path(p)
            except KeyError:
                return self._missing()
            if e.is_redirect:
                t = e.get_redirect_entry()
                return self._redirect("/z/%s/%s" % (urllib.parse.quote(pid), urllib.parse.quote(t.path, safe="/")))
            item = e.get_item()
            body = bytes(item.content)
            mt = item.mimetype or "application/octet-stream"
            if mt.startswith("text/html"):
                return self._bytes(200, _inject(body), "text/html; charset=utf-8")
            if (mt.startswith("text/") or mt in ("application/javascript", "application/json")) and "charset" not in mt:
                mt += "; charset=utf-8"
            return self._bytes(200, body, mt, "max-age=86400")

        def _rachel(self, rest):
            m, _, p = rest.partition("/")
            if ("r:" + m) not in vault.packs():
                return self._missing("That module isn't in the vault.")
            root = vault._rroot(m)
            fp = os.path.normpath(os.path.join(root, p))
            if not (fp + os.sep).startswith(os.path.normpath(root) + os.sep):
                return self._missing("Wrong address.")
            if os.path.isdir(fp):
                if not self.path.split("?")[0].endswith("/"):
                    return self._redirect(urllib.parse.quote("/r/%s/%s/" % (m, p.rstrip("/"))).replace("//", "/"))
                for idx in ("index.html", "index.htm"):
                    if os.path.isfile(os.path.join(fp, idx)):
                        return self._file(os.path.join(fp, idx))
                if os.path.normpath(fp) == os.path.normpath(root):
                    for name in ("rachel-index.php", "index.htmlf"):
                        try:
                            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
                                frag = f.read()
                        except OSError:
                            continue
                        title = (vault.packs().get("r:" + m) or {}).get("title", m)
                        return self._bytes(200, _inject(_rachel_front(m, title, frag).encode("utf-8")), "text/html; charset=utf-8", "no-cache")
                return self._listing(fp, m, p)
            if fp.lower().endswith(".php"):
                return self._missing("This page needs a web server feature Archie doesn't run. Use the Vault search box instead.")
            if not os.path.isfile(fp):
                return self._missing()
            return self._file(fp)

        def _listing(self, fp, m, p):
            try:
                names = sorted(os.listdir(fp), key=lambda s: s.lower())
            except OSError:
                return self._missing()
            items = "".join("<li><a href='%s%s'>%s</a></li>" % (urllib.parse.quote(n), "/" if os.path.isdir(os.path.join(fp, n)) else "",
                                                                 htmllib.escape(n)) for n in names if not n.startswith("."))
            body = ("<!doctype html><meta charset=utf-8><title>%s</title><body style='font-family:system-ui;padding:30px;line-height:1.6'>"
                    "<h2>%s</h2><ul>%s</ul>" % (htmllib.escape(p or m), htmllib.escape(p or m), items)).encode("utf-8")
            self._bytes(200, _inject(body), "text/html; charset=utf-8", "no-cache")

    class S(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False
    return S(("127.0.0.1", port), H)


def _inject(body):
    """Add the tiny script that tells the Vault window which page is showing (and opens PDFs in their own window)."""
    m = re.search(rb"(?i)<head[^>]*>", body[:4000])
    if m:
        return body[:m.end()] + FRAME_JS + body[m.end():]
    return FRAME_JS + body
