import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re  # 用于解析.js文件

BASE_URL = "https://dblp.org/pid/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br"
}


def fetch_publications(dblp_id):
    """
    Fetch ALL types of publications from the DBLP profile using unique ID.
    """
    url = BASE_URL + dblp_id + ".html"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()  # Active RequestException on Error
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data for {dblp_id}: {str(e)}")
        return []

    # Parse HTML to extract publication details
    soup = BeautifulSoup(response.text, 'html.parser')
    publication_list = []
    
    # Match publication entries
    for li in soup.find_all('li', class_=lambda x: x and 'entry' in x):
        title_elem = li.find('span', class_='title') or li.find('a', class_='title')
        if not title_elem:
            continue
        title = title_elem.text.strip()

        authors = []
        author_elems = li.find_all('span', itemprop="author") or li.find_all('a', class_='author')
        for auth in author_elems:
            auth_name = auth.text.strip()
            if auth_name:
                authors.append(auth_name)

        venue = 'unknown'
        venue_elem = li.find('span', itemprop='isPartOf') or li.find('em', class_='booktitle')
        if venue_elem:
            venue = venue_elem.text.strip()
        
        year = 'unknown'
        year_elem = li.find('span', class_='year') or li.find('span', itemprop='datePublished')
        if year_elem:
            year = year_elem.text.strip()

        # 构建符合图2格式的论文数据（补充默认空字段）
        publication = {
            "title": title,
            "date": year,  # 对应图2的date字段
            "authors": authors if authors else ['unknown'],
            "venue": venue,
            "venueShort": venue,  # 默认复用venue值，可根据需要自定义
            "tags": [],           # 图2格式的空tags数组
            "abstract": "",       # 空摘要
            "projectUrl": "",     # 空项目链接
            "paperUrl": "",       # 空论文链接
            "slidesUrl": "",      # 空幻灯片链接
            "bibtex": ""          # 空bibtex
        }
        publication_list.append(publication)

    return publication_list


def read_js_file(file_path):
    """
    Read the .js file and extract JSON array data from module.exports (图2格式).
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        # 匹配 module.exports = [...] 的数组部分（图2格式）
        match = re.search(r'module.exports\s*=\s*(\[.*?\]);', content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        else:
            return []  # 返回空数组作为默认


def save_to_js_file(member, data, path):
    """
    Save JSON array back as JavaScript module.exports format (.js file) - 图2格式.
    """
    # 输出 module.exports = [...] 格式（完全匹配图2）
    content = f"module.exports = {json.dumps(data, indent=2, ensure_ascii=False)};"
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def update_member_file(member, publications, collection_dir):
    """
    Update or create the .js file for the member with the new publications (图2格式).
    """
    file_name = member['json_file']
    js_file_name = file_name.replace('.json', '.js')  # Ensure .js extension
    path = os.path.join(collection_dir, js_file_name)

    # 如果文件不存在，创建空数组（图2默认格式）
    if not os.path.exists(path):
        data = []
    else:
        # 解析现有.js文件（图2的数组格式）
        data = read_js_file(path)

    # 去重：基于title判断新论文
    existing_titles = {pub['title'] for pub in data}
    new_publications = [pub for pub in publications if pub['title'] not in existing_titles]

    if new_publications:
        data.extend(new_publications)
        save_to_js_file(member, data, path)  # 保存为图2格式
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
        publications = fetch_publications(member['dblp_id'])
        print(f"Fetched total publications: {len(publications)} items.")
        update_member_file(member, publications, collection_dir)
        time.sleep(2)