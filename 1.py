import requests
from bs4 import BeautifulSoup
import os
import json
import time

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
        response.raise_for_status()  # 主动抛出HTTP异常
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data for {dblp_id}: {str(e)}")
        return []

    # Parse HTML to extract publication details
    soup = BeautifulSoup(response.text, 'html.parser')
    publication_list = []
    
    # 匹配所有类型的论文条目（inproceedings/article/book等）
    for li in soup.find_all('li', class_=lambda x: x and 'entry' in x):
        # 提取标题（核心字段，无标题则跳过）
        title_elem = li.find('span', class_='title') or li.find('a', class_='title')
        if not title_elem:
            continue
        title = title_elem.text.strip()

        # 提取作者（兼容两种HTML结构）
        authors = []
        author_elems = li.find_all('span', itemprop="author") or li.find_all('a', class_='author')
        for auth in author_elems:
            auth_name = auth.text.strip()
            if auth_name:
                authors.append(auth_name)

        # 提取会议/期刊名称（venue）
        venue = 'unknown'
        venue_elem = li.find('span', itemprop='isPartOf') or li.find('em', class_='booktitle')
        if venue_elem:
            venue = venue_elem.text.strip()

        # 提取年份（DBLP主要用class='year'，而非itemprop）
        year = 'unknown'
        year_elem = li.find('span', class_='year') or li.find('span', itemprop='datePublished')
        if year_elem:
            year = year_elem.text.strip()

        # 收集论文信息（去重空值）
        publication_list.append({
            "title": title,
            "authors": authors if authors else ['unknown'],
            "venue": venue,
            "year": year
        })

    return publication_list


def update_member_file(member, publications, collection_dir):
    """
    Update the JSON file for the member with the new publications.
    """
    file_name = member['json_file']
    path = os.path.join(collection_dir, file_name)

    # If file doesn't exist, create it with default template
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                "name": member['full_name'],
                "affiliation": "CASTLE Lab",
                "publications": []
            }, f, indent=2, ensure_ascii=False)

    # Load existing publications
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        data = {"name": member['full_name'], "affiliation": "CASTLE Lab", "publications": []}

    # 去重：基于标题判断是否为新论文
    existing_titles = {pub['title'] for pub in data['publications']}
    new_publications = [pub for pub in publications if pub['title'] not in existing_titles]

    if new_publications:
        data['publications'].extend(new_publications)
        # 保存时指定UTF-8编码，避免中文乱码
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Updated {file_name} with {len(new_publications)} new publications.")
    else:
        print(f"No updates needed for {file_name}.")


if __name__ == "__main__":
    # Set the collection directory
    collection_dir = "./collection"
    os.makedirs(collection_dir, exist_ok=True)

    # Define members' DBLP IDs and their JSON file names
    members = [
        {"dblp_id": "c/SCCheung", "full_name": "Shing-Chi Cheung", "json_file": "sccheung.json"},
        {"dblp_id": "141/2709", "full_name": "Congying Xu", "json_file": "congyingxu.json"},
        {"dblp_id": "376/1204", "full_name": "Ching Hang Mak", "json_file": "chinghangmak.json"},
        {"dblp_id": "247/3354", "full_name": "Haoyang Ma", "json_file": "haoyangma.json"},
        {"dblp_id": "262/9474", "full_name": "Hengcheng Zhu", "json_file": "hengchengzhu.json"},
        {"dblp_id": "225/0242", "full_name": "Huaxun Huang", "json_file": "huaxunhuang.json"},
        {"dblp_id": "224/1601", "full_name": "Jialun Cao", "json_file": "jialuncao.json"},
        {"dblp_id": "12/10490", "full_name": "Jiarong Wu", "json_file": "jiarongwu.json"},
        {"dblp_id": "47/5973-1", "full_name": "Lili Wei", "json_file": "liliwei.json"},
        {"dblp_id": "31/2088", "full_name": "Lu Liu", "json_file": "luliu.json"},
        {"dblp_id": "295/8585", "full_name": "Wuqi Zhang", "json_file": "wuqizhang.json"},
        {"dblp_id": "94/3104-38", "full_name": "Ying Wang", "json_file": "yingwang.json"},
        {"dblp_id": "180/5774-1", "full_name": "Yongqiang Tian", "json_file": "yongqiangtian.json"},
    ]

    # Fetch and save publications for each member
    for member in members:
        print(f"\nProcessing member: {member['full_name']} ({member['json_file']})")
        publications = fetch_publications(member['dblp_id'])
        print(f"Fetched total publications: {len(publications)} items.")
        update_member_file(member, publications, collection_dir)
        time.sleep(2)