import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re

BASE_URL = "https://dblp.org/pid/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br"
}

# 可按需扩展：从 venue 推断 venueShort（推不了就留空字符串）
VENUE_SHORT_MAP = {
    "IEEE Trans. Serv. Comput.": "TSC",
    "Proceedings of the 28th ACM Joint European SoftwareEngineering Conference and Symposium on the Foundations of Software Engineering": "ESEC/FSE",
    "42nd International Conference on Software Engineering": "ICSE",
}


def infer_venue_short(venue: str) -> str:
    venue = (venue or "").strip()
    for k, v in VENUE_SHORT_MAP.items():
        if k in venue:
            return v
    return ""


def normalize_whitespace(s: str) -> str:
    s = s or ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def fetch_publications(dblp_id):
    """
    Fetch publications from the DBLP profile using unique ID.
    Now returns items closer to the target JS schema.
    """
    url = BASE_URL + dblp_id + ".html"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data for {dblp_id}: {str(e)}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    publication_list = []

    # DBLP 条目通常在 li.entry 下
    for li in soup.find_all('li', class_=lambda x: x and 'entry' in x):
        title_elem = li.find('span', class_='title') or li.find('a', class_='title')
        if not title_elem:
            continue
        title = title_elem.text.strip()

        authors = []
        author_elems = li.find_all('span', itemprop="author") or li.find_all('a', class_='author')
        for auth in author_elems:
            name = auth.text.strip()
            if name:
                authors.append(name)

        # venue
        venue = ""
        venue_elem = li.find('span', itemprop='isPartOf') or li.find('em', class_='booktitle')
        if venue_elem:
            venue = venue_elem.text.strip()

        # year
        year = ""
        year_elem = li.find('span', class_='year') or li.find('span', itemprop='datePublished')
        if year_elem:
            year = year_elem.text.strip()

        # abstract：DBLP HTML 通常没有论文摘要（你的示例摘要来自别处），抓不到就留空
        abstract = ""

        publication_list.append({
            "title": title,
            "date": year or "",               # 按你示例用 date: "2021"
            "authors": authors or ["unknown"],
            "venue": venue or "",
            "venueShort": infer_venue_short(venue),
            "tags": [],                       # DBLP 不提供 tags，留空数组
            "abstract": abstract,             # 留空字符串，仍输出为模板字符串
            "projectUrl": "",
            "paperUrl": "",
            "slidesUrl": "",
            "bibtex": ""                      # 需要额外抓 bibtex 的话可以后续加（见下方说明）
        })

    return publication_list


def read_js_file(file_path):
    """
    Read JS file in the form:
      module.exports = [ ... ];
    Return a Python list of publication dicts.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 抓 module.exports = [ ... ]
    m = re.search(r"module\.exports\s*=\s*(\[\s*.*?\s*\])\s*;?\s*$", content, re.DOTALL)
    if not m:
        return []

    arr_text = m.group(1)

    # 这里假设数组内容是“JSON兼容”的（双引号、无尾逗号等）。
    # 我们自己写出的文件就是 JSON 兼容的，所以可直接 loads。
    try:
        return json.loads(arr_text)
    except json.JSONDecodeError:
        # 如果用户手工改过导致不是严格 JSON（比如单引号/尾逗号），就给个更明确的错误
        raise ValueError(
            f"Cannot parse {file_path}. Please ensure it is JSON-compatible like: module.exports = [ ... ];"
        )


def js_string(s: str) -> str:
    """
    JSON dumps for JS string literal.
    """
    return json.dumps(s, ensure_ascii=False)


def publication_to_js_object(pub: dict, indent: int = 4) -> str:
    """
    Render one publication object in the exact style you showed:
      {
          title: "...",
          date: "2021",
          authors: [...],
          venue: "...",
          venueShort: "...",
          tags: [...],
          abstract: `
...`,
          projectUrl: "",
          paperUrl: "",
          slidesUrl: "",
          bibtex: `
...`
      }
    """
    sp = " " * indent
    sp2 = " " * (indent + 4)

    title = pub.get("title", "")
    date = pub.get("date", "")
    authors = pub.get("authors", []) or []
    venue = pub.get("venue", "")
    venueShort = pub.get("venueShort", "")
    tags = pub.get("tags", []) or []
    abstract = normalize_whitespace(pub.get("abstract", ""))
    projectUrl = pub.get("projectUrl", "")
    paperUrl = pub.get("paperUrl", "")
    slidesUrl = pub.get("slidesUrl", "")
    bibtex = normalize_whitespace(pub.get("bibtex", ""))

    # authors/tags 用 JSON 数组格式，保证可解析
    authors_js = json.dumps(authors, indent=0, ensure_ascii=False)
    tags_js = json.dumps(tags, indent=0, ensure_ascii=False)

    # 模板字符串：里面不要反引号，否则需要转义（这里简单处理：替换成单引号）
    abstract = abstract.replace("`", "'")
    bibtex = bibtex.replace("`", "'")

    return (
        f"{sp}{{\n"
        f"{sp2}title: {js_string(title)},\n"
        f"{sp2}date: {js_string(date)},\n"
        f"{sp2}authors: {authors_js},\n"
        f"{sp2}venue: {js_string(venue)},\n"
        f"{sp2}venueShort: {js_string(venueShort)},\n"
        f"{sp2}tags: {tags_js},\n"
        f"{sp2}abstract: `\n{abstract}\n{sp2}`,\n"
        f"{sp2}projectUrl: {js_string(projectUrl)},\n"
        f"{sp2}paperUrl: {js_string(paperUrl)},\n"
        f"{sp2}slidesUrl: {js_string(slidesUrl)},\n"
        f"{sp2}bibtex: `\n{bibtex}\n{sp2}`\n"
        f"{sp}}}"
    )


def save_to_js_file(publications, path):
    """
    Save as:
      module.exports = [
        {...},
        {...}
      ]
    """
    items = [publication_to_js_object(p, indent=4) for p in publications]
    body = ",\n".join(items)
    content = "module.exports = [\n" + body + "\n]\n"

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def pub_key(pub: dict) -> str:
    # 用 title + date 去重更稳（同名不同年份）
    return f"{(pub.get('title') or '').strip()}@@{(pub.get('date') or '').strip()}"


def update_member_file(member, publications, collection_dir):
    """
    Update or create the .js file for the member with the new publications,
    with module.exports array format.
    """
    js_file_name = member['json_file']  # 你现在 members 里已经是 .js
    path = os.path.join(collection_dir, js_file_name)

    if not os.path.exists(path):
        existing_pubs = []
    else:
        existing_pubs = read_js_file(path)

    existing_keys = {pub_key(p) for p in existing_pubs}
    new_publications = [p for p in publications if pub_key(p) not in existing_keys]

    if new_publications:
        merged = existing_pubs + new_publications
        save_to_js_file(merged, path)
        print(f"Updated {js_file_name} with {len(new_publications)} new publications.")
    else:
        print(f"No updates needed for {js_file_name}.")


if __name__ == "__main__":
    collection_dir = "./collection"
    os.makedirs(collection_dir, exist_ok=True)

    members = [
        {"dblp_id": "c/SCCheung", "full_name": "Shing-Chi Cheung", "json_file": "cheung.js"},
        {"dblp_id": "141/2709", "full_name": "Congying Xu", "json_file": "Congying_Xu.js"},
        {"dblp_id": "376/1204", "full_name": "Ching Hang Mak", "json_file": "david_mak.js"},
        {"dblp_id": "247/3354", "full_name": "Haoyang Ma", "json_file": "Haoyang.js"},
        {"dblp_id": "262/9474", "full_name": "Hengcheng Zhu", "full_name": "Hengcheng Zhu", "json_file": "hengcheng.js"},
        {"dblp_id": "225/0242", "full_name": "Huaxun Huang", "json_file": "Huaxun_Huang.js"},
        {"dblp_id": "224/1601", "full_name": "Jialun Cao", "json_file": "jialun_cao.js"},
        {"dblp_id": "12/10490", "full_name": "Jiarong Wu", "json_file": "jiarong.js"},
        {"dblp_id": "47/5973-1", "full_name": "Lili Wei", "json_file": "Lili_Wei.js"},
        {"dblp_id": "31/2088", "full_name": "Lu Liu", "json_file": "Lu_Liu.js"},
        {"dblp_id": "295/8585", "full_name": "Wuqi Zhang", "json_file": "Wuqi_Aaron_Zhang.js"},
        {"dblp_id": "94/3104-38", "full_name": "Ying Wang", "json_file": "Ying.js"},
        {"dblp_id": "180/5774-1", "full_name": "Yongqiang Tian", "json_file": "Yongqiang_Tian.js"},
    ]

    for member in members:
        print(f"\nProcessing member: {member['full_name']} ({member['json_file']})")
        publications = fetch_publications(member['dblp_id'])
        print(f"Fetched total publications: {len(publications)} items.")
        update_member_file(member, publications, collection_dir)
        time.sleep(2)