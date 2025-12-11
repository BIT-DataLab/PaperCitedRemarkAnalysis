from selenium import webdriver
from selenium.webdriver.chrome.service import Service  # 导入 Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import re
import requests
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, unquote

# 扩展1个google 搜索引擎。

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

STOP_TOKENS = {"pdf", "paper", "arxiv", "openreview", "ieee", "proceedings", "www", "http", "https"}

# 可调参数
MIN_TITLE_HITS = 3          # 标题需命中多少查询 token
MIN_TITLE_OVERLAP = 0.6     # 标题命中占查询 token 的比例
MIN_PDF_SCORE = 3           # 选定 PDF 链接时的最低匹配得分
RESULTS_PER_PAGE = 30       # DuckDuckGo HTML 默认每页 30 条
MAX_PAGES = 3               # 拉取多少页搜索结果
MAX_RESULTS = 100           # 最多累计多少条结果

# 设置 Chrome 配置（无头浏览器）
def get_driver():
    options = Options()
    # 显式配置 Chrome 可执行文件和常见的无沙盒参数，避免 headless 环境下的权限/共享内存问题
    options.binary_location = "/home/lijianhui/worksp/crawl/chrome-linux64/chrome"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--user-agent={DEFAULT_HEADERS['User-Agent']}")
    driver_path = "/home/lijianhui/worksp/crawl/chromedriver-linux64/chromedriver"  # 替换为你本地的 chromedriver 路径
    
    # 设置详细的日志输出
    service = Service(executable_path=driver_path, log_path='./chromedriver.log')  # 日志路径
    
    driver = webdriver.Chrome(service=service, options=options)  # 传入 service 参数
    return driver

# 在 DuckDuckGo 上执行搜索
def search_duckduckgo(query, max_pages: int = MAX_PAGES):
    try:
        requests.get("https://duckduckgo.com", timeout=5)
    except Exception as exc:  # 网络不可用时直接返回，避免无谓的浏览器启动
        print("网络无法访问 DuckDuckGo:", exc)
        return []

    driver = get_driver()

    try:
        links = []
        for page_idx in range(max_pages):
            offset = page_idx * RESULTS_PER_PAGE
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&ia=web&s={offset}"
            driver.get(search_url)

            # 等待搜索结果加载完成，最多等待 10 秒
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.result__a'))
                )
            except TimeoutException:
                snippet = driver.page_source[:800]
                print("页面加载超时，当前 URL:", driver.current_url)
                print("页面标题:", driver.title)
                print("页面内容片段:\n", snippet)
                break

            search_results = driver.find_elements(By.CSS_SELECTOR, '.result__a')
            if not search_results:
                break

            for result in search_results:
                title = result.text
                link = result.get_attribute('href')
                links.append((title, link))
                print(f"标题: {title}")
                print(f"链接: {link}")

            if len(links) >= MAX_RESULTS:
                break

        print(f"搜索到 {len(links)} 条结果：")
        return links

    finally:
        driver.quit()


def is_pdf_url(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname and "duckduckgo.com" in parsed.hostname and parsed.path.startswith("/l"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            try:
                return unquote(qs["uddg"][0])
            except Exception:
                pass
    return url


def is_arxiv_url(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return "arxiv.org" in hostname


def arxiv_to_pdf_url(url: str) -> Optional[str]:
    url = normalize_url(url)
    parsed = urlparse(url)
    if not parsed.hostname or "arxiv.org" not in parsed.hostname:
        return None

    path = parsed.path
    if path.startswith("/pdf/"):
        # 已经是 /pdf/{id}.pdf 形式，补全 .pdf 后缀
        if path.lower().endswith(".pdf"):
            return f"https://arxiv.org{path}"
        return f"https://arxiv.org{path}.pdf"

    if path.startswith("/abs/"):
        paper_id = path.split("/abs/", 1)[1].strip("/")
        if paper_id:
            return f"https://arxiv.org/pdf/{paper_id}.pdf"

    return None


def safe_filename(title: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")
    return name or "download"


def download_pdf(url: str, title: str, dest_dir: Path = Path("downloads")) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(title)
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    target = dest_dir / filename

    print(f"下载 PDF: {url} -> {target}")
    with requests.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        with open(target, "wb") as fout:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    fout.write(chunk)
    return target


def extract_pdf_links_from_html(html: str, base_url: str):
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    pdfs = []
    for href in hrefs:
        full = urljoin(base_url, href)
        if is_pdf_url(full):
            pdfs.append(full)
    return pdfs


def get_query_tokens(query: str) -> list[str]:
    tokens = [tok for tok in re.split(r"\W+", query.lower()) if tok]
    return [tok for tok in tokens if tok not in STOP_TOKENS and len(tok) > 2]


def token_hits(text: str, tokens: list[str]) -> int:
    text_l = text.lower()
    return sum(tok in text_l for tok in tokens)


def title_score(result_title: str, query: str):
    """返回 (hits, overlap) 作为标题与查询的粗评分。"""
    tokens = get_query_tokens(query)
    if not tokens:
        return 0, 1.0
    hits = token_hits(result_title, tokens)
    overlap = hits / len(tokens)
    return hits, overlap


def score_match(text: str, query: str) -> int:
    tokens = get_query_tokens(query)
    if not tokens:
        return 0
    return token_hits(text, tokens)


def title_is_relevant(result_title: str, query: str, min_hits: int = MIN_TITLE_HITS, min_overlap: float = MIN_TITLE_OVERLAP) -> bool:
    """判定结果标题与查询是否相关，避免误下完全不相干的论文。"""
    hits, overlap = title_score(result_title, query)
    return hits >= min_hits and overlap >= min_overlap


def find_pdf_for_result(title: str, url: str, query: str):
    url = normalize_url(url)
    # 1) arXiv 入口保留，后续可替换为专用处理逻辑
    if is_arxiv_url(url):
        pdf = arxiv_to_pdf_url(url)
        if pdf:
            print(f"arXiv 链接转换为 PDF: {pdf}")
            return pdf
        print(f"发现 arXiv 链接但未能解析 PDF: {url}")
        return None

    # 2) 结果本身就是 PDF
    if is_pdf_url(url):
        return url

    # 3) 抓取页面，寻找 PDF 链接
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        print(f"获取页面失败 {url}: {exc}")
        return None

    pdf_links = extract_pdf_links_from_html(resp.text, url)
    if not pdf_links:
        print(f"页面未发现 PDF 链接: {url}")
        return None

    # 选取与 query/title 最匹配的 PDF 链接
    best = None
    best_score = -1
    combined_ref = f"{title} {resp.text[:1000]}"  # 局部文本用于粗匹配
    for pdf_url in pdf_links:
        score = score_match(pdf_url, query)
        score = max(score, score_match(combined_ref, query))
        if score > best_score:
            best = pdf_url
            best_score = score

    if best_score < MIN_PDF_SCORE:  # 命中词过少则认为不相关
        print(f"PDF 链接与查询匹配度低（score={best_score}），跳过: {best}")
        return None
    return best


def process_search_results(query: str, results):
    for title, url in results:
        if not title_is_relevant(title, query):
            print(f"跳过标题匹配度低的结果: {title}")
            continue
        print(f"处理结果: {title} -> {url}")
        pdf_url = find_pdf_for_result(title, url, query)
        if not pdf_url:
            continue
        try:
            saved_to = download_pdf(pdf_url, title)
            print(f"已下载到: {saved_to}")
            return saved_to
        except Exception as exc:
            print(f"下载失败 {pdf_url}: {exc}")
            continue
    print("未找到可用的 PDF 链接。")
    return None

# 示例查询
#query = "DIFFODE: Neural ODE with Differentiable Hidden State for Irregular Time Series Analysis pdf"
#query = "Towards Robust Trajectory Embedding for Similarity Computation: When Triangle Inequality Violations in Distance Metrics Matter pdf"
query = "GraphMaster: Automated Graph Synthesis via LLM Agents in Data-Limited Environments pdf"
results = search_duckduckgo(query)
process_search_results(query, results)
