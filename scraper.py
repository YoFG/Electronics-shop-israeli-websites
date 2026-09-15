import os
import re
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,he;q=0.8'
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

def clean_price_string(price_str):
    """Removes shekel symbols, currency codes, spaces, and commas from a price string."""
    if not price_str:
        return price_str
    # Remove currency symbols/text, commas, and extra whitespace
    cleaned = re.sub(r'[₪ILS,\s]', '', price_str)
    return cleaned.strip()

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
    """Scrapes image from direct product page."""
    if 'ksp.co.il' in url:
        ksp_img = get_ksp_direct_image(url)
        if ksp_img:
            return clean_url(ksp_img)

    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, 'html.parser')

        # OpenGraph standard
        og_img = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'og:image'})
        if og_img and og_img.get('content'):
            return clean_url(og_img['content'])

        # Twitter standard
        tw_img = soup.find('meta', attrs={'name': 'twitter:image'}) or soup.find('meta', property='twitter:image')
        if tw_img and tw_img.get('content'):
            return clean_url(tw_img['content'])

    except Exception as e:
        print(f"    [!] Error fetching image from URL ({url}): {e}")

    return None

def fetch_price_from_link(url):
    """Attempts to scrape a price directly from a product link page."""
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            raw_price = None
            
            # Common OpenGraph / Schema.org price meta tags
            price_meta = (
                soup.find('meta', property='product:price:amount') or 
                soup.find('meta', property='og:price:amount') or
                soup.find('meta', attrs={'itemprop': 'price'})
            )
            if price_meta and price_meta.get('content'):
                raw_price = price_meta['content']
            else:
                # Fallback regex search on page HTML for Shekel/Dollar prices
                matches = re.findall(r'(?:₪|\$|ILS)\s?[\d,]+(?:\.\d{2})?|[\d,]+(?:\.\d{2})?\s?(?:₪|ILS)', res.text)
                if matches:
                    raw_price = matches[0]

            if raw_price:
                return clean_price_string(raw_price)

    except Exception as e:
        print(f"    [!] Error scraping direct price link ({url}): {e}")
    return None

def process_list_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Backup protection
    with open('list_backup.txt', 'w', encoding='utf-8') as backup:
        backup.writelines(lines)

    output_lines = []
    current_model_lines = []
    current_model_name = None

    def flush_model():
        nonlocal current_model_lines, current_model_name
        if not current_model_lines:
            return

        if current_model_name:
            print(f"\nChecking Model: {current_model_name}")

            # 1. Parse store links present in this model block
            store_links = []
            for line in current_model_lines:
                trimmed = line.strip()
                if ':' in trimmed:
                    key, val = trimmed.split(':', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    if key.endswith('link') and val.startswith('http'):
                        # Clean prefix so "tms link" -> "tms"
                        store_name = key.replace('link', '').strip().strip('_').strip()
                        price_key = store_name if store_name else "price"
                        store_links.append((key, val, price_key))

            # 2. Image Logic
            has_image = any(l.strip().startswith('image:') for l in current_model_lines)
            if has_image:
                print("  [*] Image: Already exists. Skipping.")
            elif store_links:
                print(f"  [>] Fetching image from link...")
                all_urls = [url for _, url, _ in store_links]
                target_url = next((u for u in all_urls if 'ksp.co.il' not in u), all_urls[0])
                image_url = fetch_product_image_url(target_url)

                if image_url:
                    print(f"  [+] Found Image: {image_url}")
                    indent = " " * 12
                    current_model_lines.append(f"{indent}image: {image_url}\n")
                else:
                    print("  [-] Image: Failed to resolve.")
            else:
                print("  [-] Image: Skipped (No store links found).")

            # 3. Price Logic - Process every store link
            new_price_entries = []

            for key, url, price_key in store_links:
                print(f"  [>] Fetching price for store link ({key})...")
                scraped_price = fetch_price_from_link(url)

                if scraped_price:
                    print(f"  [+] Found {price_key}: {scraped_price}")
                    indent = " " * 12
                    price_line = f"{indent}{price_key}: {scraped_price}\n"

                    # Check if price entry already exists (matches "tms:", "tms_price:", or "tms price:")
                    updated_existing = False
                    for idx, line in enumerate(current_model_lines):
                        line_clean = line.strip().lower()
                        pattern = rf"^({re.escape(price_key)}|{re.escape(price_key)}_price|{re.escape(price_key)}\s+price):"
                        if re.match(pattern, line_clean):
                            current_model_lines[idx] = price_line
                            updated_existing = True
                            break

                    if not updated_existing:
                        new_price_entries.append(price_line)
                else:
                    print(f"  [-] Failed to extract price from {url}")

            # Append new price entries cleanly into current_model_lines
            if new_price_entries:
                trailing_empty = []
                while current_model_lines and current_model_lines[-1].strip() == '':
                    trailing_empty.append(current_model_lines.pop())

                current_model_lines.extend(new_price_entries)
                current_model_lines.extend(reversed(trailing_empty))

        output_lines.extend(current_model_lines)
        current_model_lines = []
        current_model_name = None

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

            current_model_lines.append(line)
        else:
            output_lines.append(line)

    flush_model()

    # Write output back to list.txt
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)

    print("\nProcessing complete! list.txt updated with fetched prices.")

if __name__ == '__main__':
    process_list_file('list.txt')
