import os
import re
import json
import glob
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置请求会话，加入自动重试策略和 User-Agent 伪装
session = requests.Session()
# 遇到 429(限流), 500, 502, 503, 504 或是连接中断时，最多重试 5 次，每次等待时间指数递增
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount('http://', HTTPAdapter(max_retries=retries))
session.mount('https://', HTTPAdapter(max_retries=retries))

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

DBLP_SEARCH_API = "https://dblp.org/search/publ/api"
DBLP_BIBTEX_API = "https://dblp.org/rec/{}.bib"

def fetch_dblp_info_by_title(title):
    params = {"q": title, "format": "json", "h": 1}
    try:
        response = session.get(DBLP_SEARCH_API, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        if not hits:
            return None
        return hits[0]["info"]
    except Exception as e:
        print(f"  [!] 获取 DBLP 失败 ({title}): {e}")
        return None

def fetch_bibtex(key):
    url = DBLP_BIBTEX_API.format(key)
    try:
        response = session.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.text.strip()
    except Exception:
        return ""

def extract_objects_from_js(js_content):
    """基于符号栈平衡提取数组中每一个 {...} 对象"""
    start_idx = js_content.find('[')
    if start_idx == -1: return []
    
    objects = []
    brace_level = 0
    in_string = False
    string_char = ''
    in_template = False
    current_obj_start = -1
    
    for i in range(start_idx, len(js_content)):
        c = js_content[i]
        
        if not in_template and c in ('"', "'"):
            if not in_string:
                in_string = True
                string_char = c
            elif string_char == c and js_content[i-1] != '\\':
                in_string = False
        elif not in_string and c == '`':
            if not in_template:
                in_template = True
            elif js_content[i-1] != '\\':
                in_template = False
                
        if in_string or in_template:
            continue
            
        if c == '{':
            if brace_level == 0:
                current_obj_start = i
            brace_level += 1
        elif c == '}':
            brace_level -= 1
            if brace_level == 0 and current_obj_start != -1:
                objects.append(js_content[current_obj_start:i+1])
                current_obj_start = -1
                
    return objects

def parse_block(block_str):
    """将提取出的 JS Object 字符串正则拆解为 Python 字典"""
    paper = {}
    
    title_match = re.search(r'["\']?title["\']?\s*:\s*["\'](.*?)(?<!\\)["\']', block_str, re.DOTALL)
    if title_match:
        paper['title'] = title_match.group(1).replace("\\'", "'").replace('\\"', '"')
    
    authors_match = re.search(r'["\']?authors["\']?\s*:\s*\[([\s\S]*?)\]', block_str)
    if authors_match:
        authors_raw = authors_match.group(1)
        paper['authors'] = re.findall(r'["\'](.*?)["\']', authors_raw)
        
    abstract_match = re.search(r'["\']?abstract["\']?\s*:\s*[`]([\s\S]*?)[`]', block_str)
    if not abstract_match:
        abstract_match = re.search(r'["\']?abstract["\']?\s*:\s*["\']([\s\S]*?)["\']', block_str)
    if abstract_match:
        paper['abstract'] = abstract_match.group(1).strip()
        
    for field in ['venue', 'venueShort', 'date', 'projectUrl', 'paperUrl', 'slidesUrl', 'arxivUrl']:
        match = re.search(rf'["\']?{field}["\']?\s*:\s*["\'](.*?)["\']', block_str)
        if match:
            paper[field] = match.group(1)
            
    tags_match = re.search(r'["\']?tags["\']?\s*:\s*\[([\s\S]*?)\]', block_str)
    if tags_match:
        tags_raw = tags_match.group(1)
        paper['tags'] = re.findall(r'["\'](.*?)["\']', tags_raw)
            
    bibtex_match = re.search(r'["\']?bibtex["\']?\s*:\s*[`]([\s\S]*?)[`]', block_str)
    if not bibtex_match:
        bibtex_match = re.search(r'["\']?bibtex["\']?\s*:\s*["\']([\s\S]*?)["\']', block_str)
    if bibtex_match:
        paper['bibtex'] = bibtex_match.group(1).strip()
        
    return paper

def format_as_js_module(papers):
    lines = ["module.exports = ["]
    for i, p in enumerate(papers):
        lines.append("  {")
        lines.append(f'    "title": {json.dumps(p.get("title", ""))},')
        lines.append(f'    "date": {json.dumps(p.get("date", ""))},')
        
        authors = p.get("authors", [])
        lines.append('    "authors": [')
        for j, author in enumerate(authors):
            comma = "," if j < len(authors) - 1 else ""
            lines.append(f'      {json.dumps(author)}{comma}')
        lines.append('    ],')
        
        lines.append(f'    "venue": {json.dumps(p.get("venue", ""))},')
        lines.append(f'    "venueShort": {json.dumps(p.get("venueShort", ""))},')
        
        tags = p.get("tags", [])
        lines.append('    "tags": [')
        if tags:
            lines.append("      " + ", ".join([json.dumps(t) for t in tags]))
        lines.append('    ],')
        
        abstract = p.get('abstract', '')
        lines.append('    "abstract": `')
        lines.append(f'{abstract}')
        lines.append('    `,')
        
        for field in ['projectUrl', 'paperUrl', 'slidesUrl', 'arxivUrl']:
            if field in p:
                lines.append(f'    "{field}": {json.dumps(p[field])},')
                
        bibtex = p.get('bibtex', '')
        lines.append('    "bibtex": `')
        lines.append(f'{bibtex}')
        lines.append('    `')
        
        if i < len(papers) - 1:
            lines.append("  },")
        else:
            lines.append("  }")
    lines.append("]")
    return "\n".join(lines)

def process_js_file(filepath):
    print(f"\nProcessing {filepath} ...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取并解析
    blocks = extract_objects_from_js(content)
    original_papers = [parse_block(b) for b in blocks if parse_block(b).get('title')]
    
    if not original_papers:
        print("  未找到有效论文或解析失败。")
        return

    updated_papers = []
    for paper in original_papers:
        title = paper.get('title')
        print(f"  -> Fetching DBLP for: {title}")
        
        dblp_info = fetch_dblp_info_by_title(title)
        
        if dblp_info:
            paper['date'] = dblp_info.get('year', paper.get('date', ''))
            
            authors_info = dblp_info.get('authors', {}).get('author', [])
            if isinstance(authors_info, dict):
                authors_info = [authors_info]
            
            # 使用 DBLP 的作者列表，去掉最后末尾编号 (例如 Name 0001 -> Name)
            paper['authors'] = [re.sub(r'\s\d+$', '', a.get('text', '')) for a in authors_info if isinstance(a, dict)]
            
            paper['venue'] = dblp_info.get('venue', paper.get('venue', ''))
            paper['paperUrl'] = dblp_info.get('ee', paper.get('paperUrl', ''))
            
            key = dblp_info.get('key', '')
            if key:
                parts = key.split('/')
                if len(parts) >= 2:
                    paper['venueShort'] = parts[1].upper()
                bib = fetch_bibtex(key)
                if bib:
                    paper['bibtex'] = bib
                    
            # 延长睡眠时间，防 DBLP 封禁
            time.sleep(2)
        else:
            print(f"     [!] DBLP 中未匹配到相关结果，保留原��数据。")
            
        updated_papers.append(paper)
        
    # 重写回文件
    new_content = format_as_js_module(updated_papers)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"  [✓] Successfully updated {filepath}")

if __name__ == "__main__":
    # 获取需要处理的所有 js 文件，您可以排除不想处理的目录
    js_files = glob.glob("collection/**/*.js", recursive=True)
    
    for js_file in js_files:
        process_js_file(js_file)
        
    print("\n✅ 所有成员文件处理完毕！")