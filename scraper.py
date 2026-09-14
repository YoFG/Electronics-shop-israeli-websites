import os
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

BRAND_NAMES = [
    'asus', 'gigabyte', 'msi', 'palit', 'pny', 
    'gainward', 'zotac', 'xfx', 'sapphire', 'powercolor', 
    'asrock', 'galax', 'inno3d', 'evga'
]

def clean_url(url):
    """Strips all whitespace, tabs, and newlines from a URL string."""
    if not url:
        return None
    return re.sub(r'\s+', '', url.strip())

def get_ksp_direct_image(url):
    """Extracts item ID from KSP URL and constructs direct CDN image link."""
    match = re.search(r'/item/(\d+)', url)
    if match:
        item_id = match.group(1)
        cdn_url = f"https://img.ksp.co.il/item/{item_id}/b_1.jpg"
        
        try:
            res = requests.head(cdn_url, headers=HEADERS, timeout=5)
            if res.status_code == 200:
                return clean_url(cdn_url)
            
            cdn_url_alt = f"https://img.ksp.co.il/item/{item_id}/b_0.jpg"
            res_alt = requests.head(cdn_url_alt, headers=HEADERS, timeout=5)
            if res_alt.status_code == 200:
                return clean_url(cdn_url_alt)
        except Exception:
            return clean_url(f"https://img.ksp.co.il/item/{item_id}/b_1.jpg")

    return None

def fetch_product_image_url(url):
    if 'ksp.co.il' in url:
        print(f"  --> Resolving KSP direct CDN image for: {url}")
        ksp_img = get_ksp_direct_image(url)
        if ksp_img:
            return clean_url(ksp_img)

    try:
        print(f"  --> Scraping image standard: {url}")
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, 'html.parser')

        # 1. OpenGraph standard
        og_img = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'og:image'})
        if og_img and og_img.get('content'):
            return clean_url(og_img['content'])

        # 2. Twitter standard
        tw_img = soup.find('meta', attrs={'name': 'twitter:image'}) or soup.find('meta', property='twitter:image')
        if tw_img and tw_img.get('content'):
            return clean_url(tw_img['content'])

    except Exception as e:
        print(f"  --> Error fetching URL: {e}")

    return None

def process_list_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    with open('list_backup.txt', 'w', encoding='utf-8') as backup:
        backup.writelines(lines)

    output_lines = []
    current_model_lines = []
    current_model_name = None
    links = []

    def flush_model():
        nonlocal current_model_lines, current_model_name, links
        if not current_model_lines:
            return

        has_image = any(l.strip().startswith('image:') for l in current_model_lines)

        if not has_image and links:
            print(f"Processing: {current_model_name}")
            
            target_url = next((u for u in links if 'ksp.co.il' not in u), links[0])
            image_url = fetch_product_image_url(target_url)

            if image_url:
                print(f"  [+] Found image: {image_url}")
                content_lines = []
                trailing_lines = []
                for line in current_model_lines:
                    if line.strip() == '' and content_lines:
                        trailing_lines.append(line)
                    else:
                        if trailing_lines:
                            content_lines.extend(trailing_lines)
                            trailing_lines = []
                        content_lines.append(line)
                
                content_lines.append(f"{' ' * 12}image: {image_url}\n")
                current_model_lines = content_lines + trailing_lines
            else:
                print("  [-] No image found.")

        output_lines.extend(current_model_lines)
        current_model_lines = []
        current_model_name = None
        links = []

    for line in lines:
        trimmed = line.strip()
        is_brand_card = any(trimmed.lower().startswith(b) for b in BRAND_NAMES)

        if is_brand_card and trimmed.endswith(':'):
            flush_model()
            current_model_name = trimmed[:-1]
            current_model_lines.append(line)
            continue

        if current_model_name:
            if trimmed and not line.startswith(' ') and not line.startswith('\t') and not is_brand_card:
                flush_model()
                output_lines.append(line)
                continue

            if ':' in trimmed:
                key, val = trimmed.split(':', 1)
                key = key.strip().lower()
                val = val.strip()

                if key.endswith('link') and val.startswith('http'):
                    links.append(val)

            current_model_lines.append(line)
        else:
            output_lines.append(line)

    flush_model()

    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)

    print("\nSuccessfully processed all models and cleaned URLs!")

if __name__ == '__main__':
    process_list_file('list.txt')