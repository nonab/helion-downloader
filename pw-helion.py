import os
import re
import requests
import base64
from tqdm import tqdm
from playwright.sync_api import sync_playwright
import argparse
from pathlib import Path
import getpass

# Sanitize filenames
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# Download file with progress bar
def download_file(url, directory, file_name, referer):
    headers = {'Referer': referer}
    response = requests.get(url, headers=headers, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    file_path = os.path.join(directory, file_name)

    with open(file_path, "wb") as file, tqdm(
        desc=f"Downloading {file_name}",
        total=total_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(chunk_size=1024):
            size = file.write(data)
            bar.update(size)

# Login function
def login(page, email, password):
    page.goto('https://helion.pl/users/login')
    page.click('button#CybotCookiebotDialogBodyButtonDecline')  # Dismiss cookie consent
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('#log_in_submit')

# Get course list
def get_courses(page):
    page.goto('https://helion.pl/users/konto/biblioteka/kursy')
    page.select_option('.perpageselects', value="100")  # Select 100 items per page
    page.wait_for_timeout(2000)  # Wait for the page to refresh

    courses = []
    items = page.query_selector_all('ul#listBooks li')
    for item in items:
        title = item.query_selector('h3.title').inner_text().strip()
        book_id = re.search(r'troya=([a-zA-Z0-9_-]+)', item.query_selector('a.buy_for_gift').get_attribute('href')).group(1)
        li_id = item.get_attribute('id').replace('item', '')
        courses.append({"id": li_id, "book_id": book_id, "title": title})
    return courses

# Download course materials and videos
def download_course(course, page, referer):
    print(f"\nPobieram: {course['title']}")
    course_directory = os.path.join(os.getcwd(), sanitize_filename(course['title']))
    os.makedirs(course_directory, exist_ok=True)

    # Get lesson links
    api_url = f"https://helion.pl/api/video/users/get-link/{course['book_id']}/{course['id']}"
    cookies = {cookie['name']: cookie['value'] for cookie in page.context.cookies()}
    headers = {
        'x-requested-with': 'XMLHttpRequest',
        'Referer': referer,
        'Cookie': "; ".join([f"{k}={v}" for k, v in cookies.items()]),
    }
    response = requests.get(api_url, headers=headers)
    data = response.json()
    data.pop('status', None)

    # Download lessons
    for count, (id, url) in enumerate(data.items(), start=1):
        base64_filename = url.split('/')[-1]
        decoded_filename = base64.b64decode(base64_filename).decode('utf-8').split('/')[-1]
        print(f"Pobieram: {decoded_filename} ({count} z {len(data)})")
        download_file(url, course_directory, decoded_filename, referer)

    # Download additional materials
    material_url = f"https://helion.pl/users/konto/pobierz-materialy/{course['book_id']}"
    material_response = requests.get(material_url, headers=headers, stream=True)
    content_disposition = material_response.headers.get('content-disposition', '')
    content_length = material_response.headers.get('content-length', '0')

    if int(content_length) > 0:
        filename_match = re.search(r'filename="?(.+?)"?($|;)', content_disposition)
        filename = filename_match.group(1) if filename_match else f"materials_{course['book_id']}.zip"
        print(f"Pobieram materiały dodatkowe: {filename}")
        download_file(material_url, course_directory, filename, referer)
def get_chromium_path():
    # Check if the script is running as a packaged executable
    if getattr(sys, 'frozen', False):
        # Path for bundled application (PyInstaller unpacked files)
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        # Construct the path to the bundled Chromium binary inside the temporary folder
        chromium_path = os.path.join(base_path, 'ms-playwright', 'chromium', 'chrome-win', 'chrome.exe')
    else:
        # Normal development environment (outside of PyInstaller packaging)
        chromium_path = "C:\\Users\\pawel\\AppData\\Local\\ms-playwright\\chromium-1148\\chrome-win\\chrome.exe"
    
    return chromium_path
# Main function
def main():
    parser = argparse.ArgumentParser(description="Logowanie do heliona")
    parser.add_argument("--email", help="Your login email", required=False)
    parser.add_argument("--password", help="Your password", required=False)
    args = parser.parse_args()
    
    email = args.email or input("Wprowadź e-mail: ")
    password = args.password or getpass.getpass("wprowadź hasło: ")
    with sync_playwright() as playwright:
        chromium = playwright.chromium
        browser = chromium.launch(executable_path=get_chromium_path(), headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # Log in
            login(page, args.email, args.password)

            # Fetch courses
            courses = get_courses(page)

            # Display course list with "Download All" option
            print("Dostępne kursy:")
            print("0: Pobierz wszystkie")
            for i, course in enumerate(courses):
                print(f"{i + 1}: {course['title']}")

            # Get user input for course selection
            selected = input("Wprowadź ID kursu (można wprowadzić kilka ID oddzielonych przecinkami lub wybrać '0' by pobrać wszystkie): ")
            if selected.strip() == "0":
                selected_courses = courses
            else:
                selected_indices = [int(x.strip()) - 1 for x in selected.split(',')]
                selected_courses = [courses[i] for i in selected_indices]

            # Download selected courses
            referer = "https://helion.pl/"
            for course in selected_courses:
                download_course(course, page, referer)

        finally:
            browser.close()

if __name__ == "__main__":
    main()
