from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, HTMLResponse
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
import os

app = FastAPI(title="Ruru Archiver API")

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def read_root():
    # Redirect to index.html
    with open(os.path.join(static_dir, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/fetch_index")
def fetch_index(name: str = Query(..., description="Account name like 幽助◆16-ZTx8e-L")):
    # Parse HN and Trip
    if '◆' in name:
        parts = name.split('◆', 1)
        hn = parts[0]
        trip = parts[1]
    else:
        hn = name
        trip = ""

    log_files = set()
    page = 1
    
    base_soup = None
    all_trs = []

    while True:
        url = f"https://ruru-jinro.net/villagerlog.jsp"
        params = {
            "hn": hn,
            "trip": trip,
            "st": page,
            "sort": "VILLAGE_NUMBER"
        }
        
        try:
            # We must use proper User-Agent to avoid being blocked
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.encoding = response.apparent_encoding
            
            if response.status_code != 200:
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            found_pagination = False
            
            for link in links:
                href = link['href']
                
                # Check if it's a log link (e.g., log6/log12345.html, log6/log12345_n.html)
                log_match = re.search(r'(log\d*/log\d+.*\.html)', href)
                if log_match:
                    log_path = log_match.group(1)
                    log_files.add(log_path)
                    # Rewrite href to local logs folder
                    filename = log_path.split('/')[-1]
                    link['href'] = f"logs/{filename}"
                    continue
                
                # Check if it's a pagination link
                if "villagerlog.jsp" in href and "st=" in href:
                    st_match = re.search(r'st=(\d+)', href)
                    if st_match:
                        target_page = st_match.group(1)
                        # We will completely remove pagination from base_soup, but we need to know if there are more pages
                        if int(target_page) > page:
                            found_pagination = True
                            
                # Optionally absolute-ize other ruru-jinro links
                elif not href.startswith(('http', 'javascript', '#', 'mailto')):
                    link['href'] = f"https://ruru-jinro.net/{href.lstrip('/')}"
            
            # Extract TRs
            tbody = soup.select_one("table#villagerlog tbody")
            if tbody:
                trs = tbody.find_all("tr", recursive=False)
                for tr in trs:
                    if tr.find("td", class_="log_4"):
                        # Pagination row, skip
                        continue
                    all_trs.append(tr)
            
            if page == 1:
                base_soup = soup
            
            if not found_pagination:
                break
                
            page += 1
            if page > 200:
                break
                
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
            
    # Merge all TRs into base_soup
    if base_soup:
        tbody = base_soup.select_one("table#villagerlog tbody")
        if tbody:
            tbody.clear()
            for tr in all_trs:
                tbody.append(tr)
                
        # Inject JavaScript for custom offline filtering
        custom_js = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    // 1. Add free word search input
    var shiboriTable = document.getElementById('shibori');
    if (shiboriTable) {
        var tbody = shiboriTable.querySelector('tbody');
        if (tbody) {
            var tr = document.createElement('tr');
            tr.innerHTML = "<td class='item' style='background-color:#ffe4e1; font-weight:bold;'>フリー検索</td><td class='value' colspan='5'><input type='text' id='custom-search' style='width: 95%; padding: 4px; border:1px solid #ccc;' placeholder='村名やプレイヤー名で一発検索！'></td>";
            tbody.insertBefore(tr, tbody.firstChild);
        }
    }

    // 2. Intercept form submit
    var form = document.querySelector('form[action="villagerlog.jsp"]');
    if (form) {
        // Prevent action
        form.removeAttribute('action');
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            var roleSelect = form.querySelector('select[name="So"]');
            var winSelect = form.querySelector('select[name="Sw"]');
            var searchInput = document.getElementById('custom-search');
            
            var selectedRole = roleSelect ? roleSelect.value : '';
            var selectedWin = winSelect ? winSelect.value : '';
            var searchText = searchInput ? searchInput.value.toLowerCase() : '';
            
            var table = document.getElementById('villagerlog');
            if (!table) return;
            
            var tbody = table.querySelector('tbody');
            if (!tbody) return;
            
            var rows = tbody.querySelectorAll('tr');
            
            rows.forEach(function(row) {
                var show = true;
                
                if (selectedRole !== '') {
                    // roleSelect values: 0=村人, 1=人狼, 2=占い師, ...
                    var pad = ("0" + selectedRole).slice(-2);
                    var targetClass = 'oc' + pad;
                    var tds = row.querySelectorAll('td');
                    if (tds.length > 4) {
                        var roleTd = tds[4];
                        var span = roleTd.querySelector('span');
                        if (!span || !span.classList.contains(targetClass)) {
                            show = false;
                        }
                    }
                }
                
                if (show && selectedWin !== '') {
                    // winSelect values: 1=勝利, 2=敗北, 3=引分, 9=廃村
                    var tds = row.querySelectorAll('td');
                    if (tds.length > 6) {
                        var winTd = tds[6];
                        var winSpan = winTd.querySelector('span');
                        var text = winTd.textContent.trim();
                        if (selectedWin === '1') {
                            if (!winSpan || !winSpan.classList.contains('win')) show = false;
                        } else if (selectedWin === '2') {
                            if (!winSpan || !winSpan.classList.contains('lose')) show = false;
                        } else if (selectedWin === '3') {
                            if (text !== '引分') show = false;
                        } else if (selectedWin === '9') {
                            if (text !== '廃村') show = false;
                        }
                    }
                }
                
                if (show && searchText !== '') {
                    if (row.textContent.toLowerCase().indexOf(searchText) === -1) {
                        show = false;
                    }
                }
                
                row.style.display = show ? '' : 'none';
            });
        });
        
        // Also trigger search on input change
        var searchInput = document.getElementById('custom-search');
        if (searchInput) {
            searchInput.addEventListener('keyup', function() {
                var evt = new Event('submit', {cancelable: true});
                form.dispatchEvent(evt);
            });
        }
    }
});
</script>
        """
        js_soup = BeautifulSoup(custom_js, 'html.parser')
        base_soup.body.append(js_soup)

    sorted_logs = sorted(list(log_files))
    
    return {
        "account": name,
        "hn": hn,
        "trip": trip,
        "merged_html": str(base_soup) if base_soup else "",
        "log_files": sorted_logs
    }

@app.get("/api/proxy")
def proxy_path(path: str = Query(..., description="Path relative to ruru-jinro.net")):
    # Ensure path doesn't start with slash for url join
    path = path.lstrip('/')
    url = f"https://ruru-jinro.net/{path}"
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            content_type = "text/html"
            if path.endswith(".css"):
                content_type = "text/css"
            elif path.endswith(".js"):
                content_type = "application/javascript"
            elif path.endswith(".woff2"):
                content_type = "font/woff2"
            elif path.endswith(".woff"):
                content_type = "font/woff"
            elif path.endswith(".ttf"):
                content_type = "font/ttf"
            elif path.endswith(".jpg") or path.endswith(".jpeg"):
                content_type = "image/jpeg"
            elif path.endswith(".png"):
                content_type = "image/png"
                
            return Response(content=response.content, media_type=content_type)
        elif response.status_code == 404:
            raise HTTPException(status_code=404, detail="File not found")
        else:
            raise HTTPException(status_code=response.status_code, detail="Error from ruru-jinro")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
