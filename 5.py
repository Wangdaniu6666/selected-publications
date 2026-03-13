import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re
from urllib.parse import urljoin

BASE_URL = "https://dblp.org/pid/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# -----------------------
# small utils
# -----------------------
def safe_get_text(el):
    return el.get_text(" ", strip=True) if el else ""

def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def fetch_text(url, timeout=15, sleep_s=0.3):
    # 小睡一下，避免对 dblp 过于频繁
    if sleep_s:
        time.sleep(sleep_s)
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text

def parse_bibtex_entry_type(bibtex: str) -> str:
    # e.g. @inproceedings{... -> inproceedings
    m = re.search(r"@\s*([a-zA-Z]+)\s*{", bibtex or "")
    return m.group(1).lower() if m else ""

def parse_bibtex_fields(bibtex: str) -> dict:
    """
    非严格 bibtex parser（足够应付 DBLP .bib 格式）
    解析类似: key = {value} / key = "value"
    """
    fields = {}
    if not bibtex:
        return fields

    # 去掉 entry header: @xxx{key,
    body = re.sub(r"^@\w+\s*{[^,]+,\s*", "", bibtex.strip(), flags=re.DOTALL)
    # 去掉最后一个 }
    body = re.sub(r"}\s*$", "", body.strip(), flags=re.DOTALL)

    # DBLP 的 bib 一般每行一个字段，但 value 可能跨行；这里用一个相对宽松的 regex 分段
    # 匹配: name = { ... } 或 name = " ... "
    # 采用“找到字段名=”，然后尽量抓到下一个 “,\n<word> =” 前
    pattern = re.compile(r"\n?\s*([a-zA-Z][a-zA-Z0-9_-]*)\s*=\s*({|\")", re.MULTILINE)
    matches = list(pattern.finditer("\n" + body))
    for i, m in enumerate(matches):
        key = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len("\n" + body)
        chunk = ("\n" + body)[start:end].strip()

        # 去掉结尾逗号
        chunk = re.sub(r",\s*$", "", chunk)

        # 去掉包裹的 { } 或 " "
        if chunk.startswith("{"):
            # 找到最后一个 }（简单处理）
            if chunk.endswith("}"):
                val = chunk[1:-1]
            else:
                val = chunk[1:]
        elif chunk.startswith('"'):
            if chunk.endswith('"'):
                val = chunk[1:-1]
            else:
                val = chunk[1:]
        else:
            val = chunk

        fields[key] = val.strip()

    return fields

def guess_paper_url(fields: dict) -> str:
    """
    优先级：doi -> ee -> url
    """
    doi = fields.get("doi", "").strip()
    ee = fields.get("ee", "").strip()
    url = fields.get("url", "").strip()

    if doi:
        # DBLP bibtex 里 doi 通常是 10.xxxx/...
        if doi.startswith("http://") or doi.startswith("https://"):
            return doi
        return "https://doi.org/" + doi

    # ee sometimes includes publisher/arxiv links
    if ee.startswith("http://") or ee.startswith("https://"):
        return ee

    if url.startswith("http://") or url.startswith("https://"):
        return url

    return ""

def extract_tags_from_bibtex(fields: dict, entry_type: str) -> list:
    """
    DBLP 不保证有 keywords，但如果有就用；
    另外把 entry_type 作为一个“弱 tag”（比如 inproceedings/article）
    其他难找的先省略。
    """
    tags = []

    keywords = fields.get("keywords", "").strip()
    if keywords:
        # 常见分隔符：逗号/分号
        parts = re.split(r"[;,]\s*", keywords)
        tags.extend([p.strip() for p in parts if p.strip()])

    if entry_type:
        tags.append(entry_type)

    # 去重保持顺序
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

# -----------------------
# main dblp parsing
# -----------------------
def parse_profile_publications(dblp_id: str):
    """
    从 DBLP profile HTML 抓基本字段 + 详情链接(rec) + bib 链接
    """
    url = BASE_URL + dblp_id + ".html"
    try:
        html = fetch_text(url, timeout=15, sleep_s=0.0)
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch profile for {dblp_id}: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    pubs = []

    for li in soup.find_all("li", class_=lambda x: x and "entry" in x):
        title_el = li.find("span", class_="title") or li.find("a", class_="title")
        if not title_el:
            continue
        title = safe_get_text(title_el)

        # authors
        authors = []
        author_elems = li.find_all("span", itemprop="author") or li.find_all("a", class_="author")
        for a in author_elems:
            name = safe_get_text(a)
            if name:
                authors.append(name)

        # year/date
        year_el = li.find("span", class_="year") or li.find("span", itemprop="datePublished")
        year = safe_get_text(year_el) or "unknown"

        # venue
        venue_el = li.find("span", itemprop="isPartOf") or li.find("em", class_="booktitle")
        venue = safe_get_text(venue_el) or "unknown"

        # dblp record link
        rec_url = ""
        bib_url = ""

        # 常见：<nav class="publ"> 里有 bib / ee / url 等链接
        nav = li.find("nav", class_="publ")
        if nav:
            for a in nav.find_all("a", href=True):
                href = a["href"].strip()
                if not href:
                    continue
                abs_url = urljoin("https://dblp.org", href)

                # bibtex link usually ends with .bib
                if abs_url.endswith(".bib"):
                    bib_url = abs_url

                # record html: /rec/...html or /rec/... (sometimes)
                if "/rec/" in abs_url and (abs_url.endswith(".html") or abs_url.endswith("/")):
                    rec_url = abs_url.rstrip("/")

        # fallback: try find any /rec/ link in li
        if not rec_url:
            a_rec = li.find("a", href=re.compile(r"^/rec/"))
            if a_rec and a_rec.get("href"):
                rec_url = urljoin("https://dblp.org", a_rec["href"])

        pub = {
            "title": title,
            "date": year,
            "authors": authors if authors else ["unknown"],
            "venue": venue,
            "venueShort": venue,   # 先保持原逻辑；后面可根据 bibtex/journal/booktitle 做进一步缩写
            "tags": [],
            "abstract": "",
            "projectUrl": "",
            "paperUrl": "",
            "slidesUrl": "",
            "bibtex": "",
            "_dblp_rec_url": rec_url,
            "_dblp_bib_url": bib_url,
        }
        pubs.append(pub)

    return pubs

def enrich_with_bibtex(pub: dict):
    """
    如果能拿到 bibtex，就补齐 paperUrl/tags/bibtex 等
    """
    bib_url = pub.get("_dblp_bib_url") or ""
    rec_url = pub.get("_dblp_rec_url") or ""

    # 若 profile 没给 bib_url，可由 rec_url 推断：把 .html 换成 .bib
    if not bib_url and rec_url:
        if rec_url.endswith(".html"):
            bib_url = rec_url[:-5] + ".bib"
        elif "/rec/" in rec_url:
            bib_url = rec_url + ".bib"

    if not bib_url:
        return pub

    try:
        bibtex = fetch_text(bib_url, timeout=15, sleep_s=0.25)
    except requests.exceptions.RequestException:
        # bib 抓不到就跳过
        return pub

    pub["bibtex"] = bibtex.strip()

    entry_type = parse_bibtex_entry_type(bibtex)
    fields = parse_bibtex_fields(bibtex)

    # paperUrl
    paper_url = guess_paper_url(fields)
    if paper_url:
        pub["paperUrl"] = paper_url

    # tags
    tags = extract_tags_from_bibtex(fields, entry_type)
    if tags:
        pub["tags"] = tags

    # venueShort: 尝试用 journal/booktitle 进一步替换（仍然很不稳定，先尽量不“乱改”）
    # 这里先不做复杂缩写，避免误判；如果你希望，我可以加一套规则表（ICSE/ASE/ISSTA/...）
    bt_venue = (fields.get("booktitle") or fields.get("journal") or "").strip()
    if bt_venue and (pub.get("venue") == "unknown" or len(pub.get("venue", "")) < len(bt_venue)):
        pub["venue"] = bt_venue
        pub["venueShort"] = pub["venueShort"] or bt_venue

    return pub

# -----------------------
# js file read/write (keep same as 4.py)
# -----------------------
def read_js_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        match = re.search(r"module\.exports\s*=\s*(\[\s*.*?\s*\])\s*;?\s*$", content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return []

def save_to_js_file(data, path):
    content = f"module.exports = {json.dumps(data, indent=2, ensure_ascii=False)};"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def update_member_file(member, publications, collection_dir):
    js_file_name = member["json_file"]
    path = os.path.join(collection_dir, js_file_name)

    if not os.path.exists(path):
        data = []
    else:
        data = read_js_file(path)

    existing_titles = {pub.get("title", "") for pub in data}
    new_publications = [pub for pub in publications if pub.get("title", "") not in existing_titles]

    if new_publications:
        # 写入前把内部临时字段去掉
        for p in new_publications:
            p.pop("_dblp_rec_url", None)
            p.pop("_dblp_bib_url", None)

        data.extend(new_publications)
        save_to_js_file(data, path)
        print(f"Updated {js_file_name} with {len(new_publications)} new publications.")
    else:
        print(f"No updates needed for {js_file_name}.")

if __name__ == "__main__":
    collection_dir = "./collection"
    os.makedirs(collection_dir, exist_ok=True)

    members = [
        {"dblp_id": "c/SCCheung", "full_name": "Shing-Chi Cheung", "json_file": "cheung.js"},
        # {"dblp_id": "141/2709", "full_name": "Congying Xu", "json_file": "Congying_Xu.js"},
        # {"dblp_id": "376/1204", "full_name": "Ching Hang Mak", "json_file": "david_mak.js"},
        # {"dblp_id": "247/3354", "full_name": "Haoyang Ma", "json_file": "Haoyang.js"},
        # {"dblp_id": "262/9474", "full_name": "Hengcheng Zhu", "json_file": "hengcheng.js"},
        # {"dblp_id": "225/0242", "full_name": "Huaxun Huang", "json_file": "Huaxun_Huang.js"},
        # {"dblp_id": "224/1601", "full_name": "Jialun Cao", "json_file": "jialun_cao.js"},
        # {"dblp_id": "12/10490", "full_name": "Jiarong Wu", "json_file": "jiarong.js"},
        # {"dblp_id": "47/5973-1", "full_name": "Lili Wei", "json_file": "Lili_Wei.js"},
        # {"dblp_id": "31/2088", "full_name": "Lu Liu", "json_file": "Lu_Liu.js"},
        # {"dblp_id": "295/8585", "full_name": "Wuqi Zhang", "json_file": "Wuqi_Aaron_Zhang.js"},
        # {"dblp_id": "94/3104-38", "full_name": "Ying Wang", "json_file": "Ying.js"},
        # {"dblp_id": "180/5774-1", "full_name": "Yongqiang Tian", "json_file": "Yongqiang_Tian.js"},
    ]

    for member in members:
        print(f"\nProcessing member: {member['full_name']} ({member['json_file']})")

        pubs = parse_profile_publications(member["dblp_id"])
        print(f"Fetched base publications: {len(pubs)} items.")

        # enrich
        enriched = []
        for p in pubs:
            enriched.append(enrich_with_bibtex(p))

        update_member_file(member, enriched, collection_dir)

        # member 间隔更久一点
        time.sleep(1.0)