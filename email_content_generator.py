# 功能：抓取 AI 与半导体相关新闻源，筛选去重后调用 LLM 生成邮件正文和主题，并用脚本追加信源。
# 输入：.env 中的 OpenRouter 配置、RSS/Web 新闻源内容、LLM 生成结果。
# 输出：generate_weekly_email() 返回 (邮件主题, 邮件正文, 新闻日期)；正文中的新闻条目会追加来源链接或来源描述。
import os
import re
import time
import html as html_module
import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone

import requests
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

from checkpoint_manager import get_checkpoint_step, load_checkpoint, save_checkpoint_step

load_dotenv(override=True)

# ================= 配置区域 =================
# OpenRouter API
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "your-openrouter-api-key")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "deepseek/deepseek-v4-pro"

# RSS 源
RSS_URL = "https://daily.juya.uk/rss.xml"

# ================= AI HOT 每日精选（与 Juya RSS 并列的 AI 日报源） =================
AI_HOT_BASE_URL = "https://aihot.virxact.com"
AI_HOT_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ================= 多源半导体与AI新闻配置 =================
# 新增 RSS/Web 来源列表
FEEDS = [
    # 标准 RSS 2.0 源
    {"url": "https://semiengineering.com/feed/", "name": "Semiconductor Engineering", "type": "rss"},
    {"url": "https://www.semiconductor-digest.com/feed/", "name": "Semiconductor Digest", "type": "rss"},
    {"url": "https://semiwiki.com/feed/", "name": "SemiWiki", "type": "rss"},
    {"url": "https://gf.com/feed/", "name": "GlobalFoundries", "type": "rss"},
    # 需要特殊处理的源
    {"url": "https://news.synopsys.com/index.php?s=20295&page=1&item=feed", "name": "Synopsys News", "type": "synopsys_html"},
    {"url": "https://www.cadence.com/en_US/home/company/newsroom/press-releases.rss", "name": "Cadence Press", "type": "cadence_rss"},
    {"url": "https://www.digitimes.com/calendar.php?d=7d", "name": "DIGITIMES", "type": "digitimes_html"},
]

# ========== 关键词分类（四大关注方向） ==========

# 1. 智能体架构 / 提示词工程 / Context Engineering
AGENT_ARCH_KEYWORDS = [
    # 智能体架构
    "agent", "agentic", "multi-agent", "agent architecture", "agent framework",
    "autonomous agent", "agent swarm", "agent orchestration", "agent collaboration",
    "open claw", "open-source agent", "agent protocol", "agent interoperability",
    "agent memory", "agent planning", "agent reasoning chain",
    # 提示词工程
    "prompt engineering", "prompt optimization", "prompt design", "system prompt",
    "few-shot", "chain of thought", "tree of thought", "react prompting",
    "automatic prompt", "DSPy", "prompt tuning",
    # Context Engineering
    "context engineering", "context window", "context management", "long context",
    "context optimization", "context compression", "memory management",
    "retrieval augmented", "RAG", "vector search", "embedding",
    # 工具与协议
    "tool use", "function calling", "MCP", "model context protocol",
    "tool integration", "API agent",
    # 大模型
    "LLM", "large language model", "AI model", "GPT", "Claude", "Copilot",
    "reasoning", "deep learning model", "transformer", "fine-tun",
    # 中文
    "智能体", "大模型", "AI代理", "agent系统", "提示词工程",
    "上下文工程", "多智能体",
]

# 2. AI for Science（科学智能）
AI_SCIENCE_KEYWORDS = [
    "AI for science", "scientific AI", "scientific discovery",
    "AlphaFold", "protein structure", "protein folding",
    "molecular dynamics", "molecular simulation",
    "drug discovery", "drug design", "computational drug",
    "materials science", "materials discovery", "materials informatics",
    "genomics", "genomic", "proteomics",
    "computational chemistry", "computational physics", "computational biology",
    "quantum chemistry", "DFT", "density functional",
    "AI physics", "AI chemistry", "AI biology",
    "scientific computing", "simulation AI", "digital twin",
    "AI for material", "deep learning science",
    "科学智能", "AI科学", "蛋白质结构", "药物发现",
    "材料科学", "计算化学",
]

# 3. AI for 智能制造与半导体晶圆代工（偏向 Foundry）
SMART_MFG_KEYWORDS = [
    # 晶圆制造核心
    "wafer", "fab", "foundry", "lithography", "EUV", "semiconductor",
    "chip manufacturing", "process node", "nanomet", "angstrom",
    "FinFET", "GAA", "CFET", "nanosheet", "forksheet",
    "backside power", "backside contact",
    # 代工厂商
    "TSMC", "Intel Foundry", "Samsung Foundry", "GlobalFoundries",
    "SMIC", "UMC", "Rapidus",
    # 制造工艺
    "yield", "metrology", "inspection", "deposition", "etch",
    "silicon", "SoC", "semiconductor manufacturing", "chiplet",
    "advanced node", "node process", "process control",
    # 封装
    "advanced packaging", "heterogeneous integration", "3D-IC",
    "chiplet integration", "CoWoS", "EMIB",
    # 智能制造 / AI 制造
    "smart manufacturing", "intelligent manufacturing", "Industry 4.0",
    "predictive maintenance", "defect detection", "anomaly detection",
    "process optimization", "quality control", "automation",
    "digital twin", "manufacturing AI", "AI yield",
    "robotics manufacturing", "factory automation",
    "AI process control", "data-driven manufacturing",
    # 中文
    "晶圆", "芯片制造", "代工", "制程", "光刻", "封装", "良率",
    "智能制造", "晶圆代工", "半导体制造", "先进制程",
]

# 4. AI for EDA 辅助设计 / 集成电路设计
EDA_AI_KEYWORDS = [
    # EDA 工具
    "EDA", "electronic design automation",
    "Synopsys", "Cadence", "Mentor Graphics", "Siemens EDA",
    "Ansys", "Keysight",
    # AI EDA
    "DSO.ai", "Cerebrus", "AI EDA", "ML EDA",
    "AI-assisted design", "machine learning chip design",
    "AI chip design", "reinforcement learning design",
    # IC 设计流程
    "IC design", "integrated circuit design", "chip design",
    "RTL design", "RTL-to-GDS", "physical design",
    "place and route", "timing closure", "clock tree",
    "logic synthesis", "high-level synthesis",
    "floorplan", "power optimization", "area optimization",
    # 验证与签核
    "verification", "DFT", "design for test",
    "signoff", "sign-off", "static timing",
    "formal verification", "functional verification",
    # 模拟/混合信号
    "analog design", "mixed-signal", "SPICE", "circuit simulation",
    "analog automation", "analog layout",
    # 其他
    "semiconductor design", "VLSI", "ASIC", "FPGA design",
    "硅验证", "芯片设计", "集成电路", "EDA工具",
    "设计自动化",
]

def fetch_rss() -> str:
    """获取 RSS XML 内容"""
    logging.info("正在获取 RSS 内容...")
    for i in range(3):
        try:
            resp = requests.get(RSS_URL, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            logging.info(f"RSS 获取成功，内容长度: {len(resp.text)} 字符")
            return resp.text
        except requests.ConnectionError as e:
            if i < 2:
                wait = (i + 1) * 5
                logging.warning(f"RSS 请求连接失败 (第{i+1}次): {e}，{wait}秒后重试...")
                time.sleep(wait)
            else:
                raise


# ================= 多源 RSS/Web 新闻获取 =================

def _http_get(url: str, headers: dict | None = None, max_retries: int = 3) -> str | None:
    """通用 HTTP GET 请求，带重试逻辑"""
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, text/html, */*",
    }
    if headers:
        default_headers.update(headers)

    for i in range(max_retries):
        try:
            resp = requests.get(url, headers=default_headers, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.ConnectionError as e:
            if i < max_retries - 1:
                wait = (i + 1) * 5
                logging.warning(f"HTTP 请求失败 (第{i+1}次): {e}，{wait}秒后重试...")
                time.sleep(wait)
            else:
                raise
    return None


def _strip_html(text: str | None) -> str:
    """清洗 HTML 标签，返回纯文本"""
    if not text:
        return ""
    text = re.sub(r"<(script|style).*?>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<img.*?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</(h1|h2|h3|h4|p|li|div|br)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<.*?>", "", text)
    text = html_module.unescape(text)
    text = text.replace("&nbsp;", " ").replace("&gt;", ">").replace("&lt;", "<")
    # 清理多余空白
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


def _extract_links_from_html(text: str | None) -> list[str]:
    """按出现顺序从 HTML/文本中提取链接。"""
    if not text:
        return []

    text = html_module.unescape(text)
    links: list[str] = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.IGNORECASE):
        links.append(href.strip())
    for url in re.findall(r"https?://[^\s\"'<>)）]+", text):
        links.append(url.strip())

    seen = set()
    result = []
    for link in links:
        if link and link not in seen:
            seen.add(link)
            result.append(link)
    return result


def _source_label_from_link(link: str) -> str:
    """根据链接域名生成来源名称。"""
    lower = link.lower()
    if "x.com/" in lower or "twitter.com/" in lower:
        return "X/Twitter"
    if "arxiv.org" in lower:
        return "arXiv"
    if "openreview.net" in lower:
        return "OpenReview"
    if "doi.org" in lower:
        return "DOI"

    match = re.search(r"https?://(?:www\.)?([^/]+)", link)
    if match:
        return match.group(1)
    return "原始信源"


def _pick_original_link_from_secondary_source(article: dict, aggregator_domains: tuple[str, ...]) -> tuple[str, str] | None:
    """从二手聚合源条目中挑选最早/原始信息链接。"""
    raw_text = "\n".join(
        str(article.get(key, ""))
        for key in ("raw_description", "raw_content", "description")
    )
    links = _extract_links_from_html(raw_text)
    if not links:
        return None

    preferred_markers = (
        "x.com/", "twitter.com/", "arxiv.org", "openreview.net",
        "doi.org", ".pdf", "github.com",
    )

    def is_external(link: str) -> bool:
        lower = link.lower()
        return not any(domain in lower for domain in aggregator_domains)

    external_links = [link for link in links if is_external(link)]
    if not external_links:
        return None

    for marker in preferred_markers:
        for link in external_links:
            if marker in link.lower():
                return link, _source_label_from_link(link)

    first_link = external_links[0]
    return first_link, _source_label_from_link(first_link)


def validate_generation_config():
    """在开始抓取和调用 LLM 前校验必要配置。"""
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your-openrouter-api-key":
        raise RuntimeError("缺少 OPENROUTER_API_KEY，请在 .env 中配置 OpenRouter API Key")


def _as_utc_aware(dt: datetime) -> datetime:
    """统一 RSS 日期为 UTC aware datetime，避免 naive/aware 比较异常。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_rss_date(date_str: str | None) -> datetime | None:
    """解析 RSS pubDate 为 datetime 对象"""
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        return _as_utc_aware(parsedate_to_datetime(date_str))
    except Exception:
        # 尝试常见格式
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
            try:
                return _as_utc_aware(datetime.strptime(date_str, fmt))
            except ValueError:
                continue
    return None


def fetch_rss_feed(url: str, source_name: str) -> list[dict]:
    """使用 xml.etree.ElementTree 解析标准 RSS 2.0 feed，仅返回最近7天文章"""
    logging.info(f"[{source_name}] 正在获取 RSS feed...")
    raw = _http_get(url)
    if not raw:
        logging.warning(f"[{source_name}] 获取内容为空")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        logging.warning(f"[{source_name}] XML 解析失败: {e}")
        return []

    # 查找所有 item 元素（兼容 RSS 命名空间）
    items = root.findall(".//item")
    if not items:
        # 尝试 Atom feed 格式
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//atom:entry", ns)
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    # 7天前（168小时），保留最近一周内的文章
    cutoff_date = datetime.now(timezone.utc) - timedelta(hours=168)
    articles = []

    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        desc_el = item.find("description")
        # Atom 兼容
        if pubdate_el is None:
            pubdate_el = item.find("{http://www.w3.org/2005/Atom}updated")
        if desc_el is None:
            desc_el = item.find("{http://www.w3.org/2005/Atom}summary")

        title = title_el.text if title_el is not None and title_el.text else ""
        link = link_el.text if link_el is not None and link_el.text else ""
        # RSS link 可能在 href 属性
        if not link and link_el is not None:
            link = link_el.get("href", "")
        pubdate = pubdate_el.text if pubdate_el is not None and pubdate_el.text else ""
        description = desc_el.text if desc_el is not None and desc_el.text else ""
        raw_description = description
        raw_content = ""

        # 尝试获取 content:encoded（WordPress 站点常见，含完整正文）
        content_encoded_el = item.find(
            "{http://purl.org/rss/1.0/modules/content/}encoded"
        )
        if content_encoded_el is not None and content_encoded_el.text:
            # 用 content:encoded 补充 description（用于更准确的关键词匹配）
            full_text = content_encoded_el.text
            raw_content = full_text
            description = (
                f"{description}\n{_strip_html(full_text)[:500]}"
                if description
                else _strip_html(full_text)[:500]
            )

        # 获取分类
        categories = [c.text for c in item.findall("category") if c.text]

        # 过滤非7天内文章
        parsed_date = _parse_rss_date(pubdate)
        if parsed_date and parsed_date < cutoff_date:
            continue

        articles.append({
            "title": _strip_html(title),
            "link": link.strip(),
            "date": pubdate,
            "description": _strip_html(description),
            "source": source_name,
            "categories": categories,
            "raw_description": raw_description,
            "raw_content": raw_content,
        })

    logging.info(f"[{source_name}] 获取 {len(articles)} 篇文章")
    return articles


def fetch_synopsys_news() -> list[dict]:
    """获取 Synopsys 新闻（HTML 页面，尝试多种方式）"""
    source_name = "Synopsys News"
    logging.info(f"[{source_name}] 正在获取新闻...")

    # 尝试不同的 feed 参数
    alt_urls = [
        "https://news.synopsys.com/index.php?s=20295&page=1&item=rss",
        "https://news.synopsys.com/index.php?s=20295&page=1&item=xml",
        "https://news.synopsys.com/index.php?s=20295&page=1&item=feed",
    ]

    for alt_url in alt_urls:
        try:
            raw = _http_get(alt_url)
            if not raw:
                continue
            # 检查是否是 RSS/XML
            if raw.strip().startswith("<?xml") or raw.strip().startswith("<rss"):
                return fetch_rss_feed(alt_url, source_name)
            # 尝试从 HTML 中提取
            articles = _scrape_synopsys_html(raw)
            if articles:
                return articles
        except Exception as e:
            logging.debug(f"[{source_name}] URL {alt_url} 失败: {e}")

    logging.warning(f"[{source_name}] 所有 URL 尝试均失败")
    return []


def _scrape_synopsys_html(html_content: str) -> list[dict]:
    """从 Synopsys news HTML 页面中提取新闻条目"""
    articles = []
    # 匹配新闻标题和链接模式 (常见 PR Newswire 格式)
    pattern = re.compile(
        r'<a[^>]*href="([^"]*20295[^"]*)"[^>]*>\s*([^<]{10,200}?)\s*</a>',
        re.IGNORECASE
    )
    matches = pattern.findall(html_content)
    for link, title in matches[:20]:
        articles.append({
            "title": _strip_html(title),
            "link": link,
            "date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
            "description": "",
            "source": "Synopsys News",
            "categories": [],
        })
    if articles:
        logging.info(f"[Synopsys News] HTML 提取到 {len(articles)} 篇文章")
    return articles


def fetch_cadence_news() -> list[dict]:
    """获取 Cadence 新闻（Cloudflare 保护，尝试绕过）"""
    source_name = "Cadence Press"
    logging.info(f"[{source_name}] 正在获取 RSS...")

    # 尝试带完整浏览器头的请求
    extra_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    try:
        raw = _http_get(
            "https://www.cadence.com/en_US/home/company/newsroom/press-releases.rss",
            headers=extra_headers,
            max_retries=2,
        )
        if raw and (raw.strip().startswith("<?xml") or raw.strip().startswith("<rss")):
            return fetch_rss_feed(
                "https://www.cadence.com/en_US/home/company/newsroom/press-releases.rss",
                source_name,
            )
    except Exception as e:
        logging.warning(f"[{source_name}] 直接访问 RSS 失败: {e}")

    # 尝试从 HTML 新闻页面抓取
    try:
        html_url = "https://www.cadence.com/en_US/home/company/newsroom/press-releases.html"
        raw = _http_get(html_url, headers=extra_headers, max_retries=2)
        if raw:
            articles = _scrape_cadence_html(raw)
            if articles:
                return articles
    except Exception as e:
        logging.warning(f"[{source_name}] HTML 抓取也失败: {e}")

    logging.warning(f"[{source_name}] 无法获取任何新闻")
    return []


def _scrape_cadence_html(html_content: str) -> list[dict]:
    """从 Cadence 新闻页面 HTML 中提取新闻条目"""
    articles = []
    # 查找包含年份的链接（新闻发布日期通常格式为 2025/2026）
    pattern = re.compile(
        r'<a[^>]*href="([^"]*press[^"]*)"[^>]*>\s*([^<]{15,200}?)\s*</a>',
        re.IGNORECASE,
    )
    matches = pattern.findall(html_content)
    for link, title in matches[:20]:
        if any(kw in title.lower() for kw in ["semiconductor", "chip", "eda", "wafer",
                                                "foundry", "ai", "design"]):
            articles.append({
                "title": _strip_html(title),
                "link": link if link.startswith("http") else f"https://www.cadence.com{link}",
                "date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
                "description": "",
                "source": "Cadence Press",
                "categories": [],
            })
    if articles:
        logging.info(f"[Cadence Press] HTML 提取到 {len(articles)} 篇文章")
    return articles


def fetch_digitimes_news() -> list[dict]:
    """获取 DIGITIMES 新闻（动态 JS 渲染页面，尽力抓取）"""
    source_name = "DIGITIMES"
    logging.info(f"[{source_name}] 正在获取新闻...")

    extra_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # 尝试多个 URL
    urls_to_try = [
        "https://www.digitimes.com/calendar.php?d=7d",
        "https://www.digitimes.com/news/",
    ]

    for url in urls_to_try:
        try:
            raw = _http_get(url, headers=extra_headers, max_retries=2)
            if not raw:
                continue

            # 搜索嵌入的 JSON 数据或 script 标签中的数据
            articles = _extract_digitimes_articles(raw)
            if articles:
                return articles
        except Exception as e:
            logging.warning(f"[{source_name}] URL {url} 失败: {e}")

    logging.warning(f"[{source_name}] 无法获取任何新闻")
    return []


def _extract_digitimes_articles(html_content: str) -> list[dict]:
    """从 DIGITIMES HTML 提取文章链接和标题"""
    articles = []
    # 查找所有可能的新闻链接
    link_patterns = [
        # 标准 href 模式
        re.compile(r'<a[^>]*href="(/news/[^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL),
        re.compile(r'<a[^>]*href="(https?://www\.digitimes\.com[^"]*)"[^>]*>(.*?)</a>',
                   re.IGNORECASE | re.DOTALL),
    ]

    seen_titles = set()
    for pattern in link_patterns:
        for link, title_raw in pattern.findall(html_content)[:30]:
            title = _strip_html(title_raw)
            if len(title) > 15 and title not in seen_titles:
                seen_titles.add(title)
                full_link = link if link.startswith("http") else f"https://www.digitimes.com{link}"
                articles.append({
                    "title": title,
                    "link": full_link,
                    "date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
                    "description": "",
                    "source": "DIGITIMES",
                    "categories": [],
                })

    if articles:
        logging.info(f"[DIGITIMES] HTML 提取到 {len(articles)} 篇文章")
    return articles


def extract_weekly_news(raw_html: str) -> tuple[str, str]:
    """从 Juya RSS HTML 中提取最近7天的新闻内容"""
    # 生成最近7天的日期列表
    today = datetime.now()
    date_list = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    all_content: list[str] = []
    matched_dates: list[str] = []

    for date_str in date_list:
        pattern = rf"<title>{date_str}</title>(.*?)(?=<title>\d{{4}}-\d{{2}}-\d{{2}}</title>|$)"
        match = re.search(pattern, raw_html, flags=re.DOTALL)
        if match:
            day_content = match.group(1)

            # 清洗 HTML 标签
            day_content = re.sub(
                r"<(script|style).*?>.*?</\1>", "", day_content, flags=re.DOTALL | re.IGNORECASE
            )
            day_content = re.sub(r"<img.*?>", "", day_content, flags=re.IGNORECASE)
            day_content = re.sub(
                r"</(h1|h2|h3|h4|p|li|div)>", "\n", day_content, flags=re.IGNORECASE
            )
            day_content = re.sub(r"<.*?>", "", day_content)

            # 符号清理
            day_content = day_content.replace("↗", "")
            day_content = re.sub(r"#\d+", "", day_content)
            day_content = day_content.replace("&nbsp;", " ").replace("&gt;", ">").replace("&lt;", "<")

            lines = [line.strip() for line in day_content.split("\n") if line.strip()]
            if lines:
                source_note = f"信源: Juya AI Daily RSS（{RSS_URL}），日期: {date_str}"
                all_content.append(f"--- {date_str} ---\n{source_note}\n" + "\n".join(lines))
                matched_dates.append(date_str)

    if not all_content:
        logging.warning(f"未找到最近7天内任何日期的新闻内容")
        return "", today.strftime("%Y-%m-%d")

    final_text = "\n\n".join(all_content)
    start_date = matched_dates[-1]  # 最早匹配到的日期
    end_date = matched_dates[0]     # 最晚匹配到的日期

    logging.info(
        f"每周新闻提取完成: 匹配到 {len(matched_dates)} 天 "
        f"({start_date} ~ {end_date}), 总内容长度: {len(final_text)} 字符"
    )
    return final_text, end_date


def _aihot_get_json(path: str, params: dict | None = None) -> dict | None:
    """请求 AI HOT 公共 API，返回 JSON 数据。"""
    url = f"{AI_HOT_BASE_URL}{path}"
    resp = requests.get(
        url,
        headers=AI_HOT_API_HEADERS,
        params=params,
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _get_recent_aihot_daily_index(take: int = 7) -> list[dict]:
    """获取最近 N 期 AI HOT 日报索引。"""
    data = _aihot_get_json("/api/public/dailies", params={"take": take})
    if not data:
        return []
    items = data.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("date")]


def _get_aihot_daily(date_str: str) -> dict | None:
    """获取某一天 AI HOT 日报详情。"""
    return _aihot_get_json(f"/api/public/daily/{date_str}")


def _first_text(*values) -> str:
    """返回第一个非空文本字段。"""
    for value in values:
        if value is None:
            continue
        text = _strip_html(str(value)).strip()
        if text:
            return text
    return ""


def _aihot_item_to_article(item: dict, daily: dict, category: str) -> dict | None:
    """将 AI HOT API 条目转换成项目内部文章结构。"""
    title = _first_text(item.get("title"), item.get("headline"), item.get("name"))
    description = _first_text(
        item.get("summary"),
        item.get("description"),
        item.get("content"),
        item.get("abstract"),
    )
    if not title and not description:
        return None

    link = _first_text(
        item.get("sourceUrl"),
        item.get("url"),
        item.get("link"),
        item.get("href"),
    )
    source = _first_text(item.get("sourceName"), item.get("source"), item.get("site"))
    if not source:
        source = _source_label_from_link(link) if link else "原始信源"

    date_str = _first_text(
        item.get("publishedAt"),
        item.get("date"),
        daily.get("generatedAt"),
        daily.get("date"),
    )
    categories = [category] if category else []

    return {
        "title": title,
        "link": link,
        "date": date_str,
        "description": description,
        "source": source,
        "categories": categories,
        "aggregator_source": "AI HOT 每日精选",
        "aggregator_link": f"{AI_HOT_BASE_URL}/daily/{daily.get('date', '')}",
    }


def _extract_aihot_articles_from_daily(daily: dict) -> list[dict]:
    """从单日 AI HOT 日报详情中提取文章列表。"""
    articles: list[dict] = []

    def append_items(items, category: str) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            article = _aihot_item_to_article(item, daily, category)
            if article:
                articles.append(article)

    sections = daily.get("sections", [])
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            category = _first_text(section.get("label"), section.get("title"), section.get("name"))
            append_items(section.get("items"), category)

    append_items(daily.get("items"), "")
    append_items(daily.get("flashes"), "快讯")

    lead = daily.get("lead")
    if isinstance(lead, dict):
        article = _aihot_item_to_article(lead, daily, "头条")
        if article:
            articles.insert(0, article)

    return articles


def fetch_aihot_news() -> str:
    """获取 AI HOT 每日精选（与 Juya RSS 并列的 AI 日报源），返回格式化文本"""
    source_name = "AI HOT 每日精选"
    logging.info(f"[{source_name}] 正在获取 AI 行业动态...")

    try:
        daily_index = _get_recent_aihot_daily_index(7)
        if not daily_index:
            logging.warning(f"[{source_name}] 未获取到日报索引")
            return ""

        articles: list[dict] = []
        for index, item in enumerate(daily_index):
            date_str = item["date"]
            logging.info(f"[{source_name}] 正在获取 {date_str} 日报...")
            daily = _get_aihot_daily(date_str)
            if daily is None:
                logging.warning(f"[{source_name}] {date_str} 不存在日报")
                continue

            daily_articles = _extract_aihot_articles_from_daily(daily)
            logging.info(
                f"[{source_name}] {date_str} 提取 {len(daily_articles)} 条"
            )
            articles.extend(daily_articles)

            if index < len(daily_index) - 1:
                time.sleep(0.3)

        if not articles:
            logging.warning(f"[{source_name}] 未获取到日报条目")
            return ""

        # 按四大方向关键词过滤
        relevant = [a for a in articles if is_relevant_article(a)]
        logging.info(
            f"[{source_name}] 获取 {len(articles)} 篇, 相关 {len(relevant)} 篇"
        )
        return format_articles_for_llm(relevant)
    except Exception as e:
        logging.warning(f"[{source_name}] 获取失败: {e}")
        return ""


# ================= 多源新闻聚合与过滤 =================

def is_relevant_article(article: dict) -> bool:
    """检查文章是否与四大关注方向相关：
    1. 智能体架构 / 提示词工程 / Context Engineering
    2. AI for Science
    3. AI for 智能制造与半导体晶圆代工
    4. AI for EDA 辅助设计与集成电路设计
    """
    text = (
        f"{article.get('title', '')} "
        f"{article.get('description', '')} "
        f"{' '.join(article.get('categories', []))}"
    )
    text_lower = text.lower()

    matches_agent = any(kw.lower() in text_lower for kw in AGENT_ARCH_KEYWORDS)
    matches_science = any(kw.lower() in text_lower for kw in AI_SCIENCE_KEYWORDS)
    matches_mfg = any(kw.lower() in text_lower for kw in SMART_MFG_KEYWORDS)
    matches_eda = any(kw.lower() in text_lower for kw in EDA_AI_KEYWORDS)

    return matches_agent or matches_science or matches_mfg or matches_eda


def _classify_article(article: dict) -> list[str]:
    """判断文章属于哪些分类"""
    text = (
        f"{article.get('title', '')} "
        f"{article.get('description', '')} "
        f"{' '.join(article.get('categories', []))}"
    ).lower()

    tags = []
    if any(kw.lower() in text for kw in AGENT_ARCH_KEYWORDS):
        tags.append("Agent架构")
    if any(kw.lower() in text for kw in AI_SCIENCE_KEYWORDS):
        tags.append("AI for Science")
    if any(kw.lower() in text for kw in SMART_MFG_KEYWORDS):
        tags.append("智能制造/晶圆代工")
    if any(kw.lower() in text for kw in EDA_AI_KEYWORDS):
        tags.append("EDA/IC设计")

    return tags


def format_articles_for_llm(articles: list[dict]) -> str:
    """将文章列表格式化为 LLM 可读的文本"""
    if not articles:
        return "（本周无相关AI与半导体新闻）"

    lines = []
    for i, a in enumerate(articles, 1):
        tags = _classify_article(a)
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        lines.append(f"{i}. [{a['source']}]{tag_str} {a['title']}")
        lines.append(f"   信源: {a['source']}")
        lines.append(f"   链接: {a['link']}")
        if a.get("aggregator_source"):
            lines.append(f"   聚合源: {a['aggregator_source']}")
        lines.append(f"   日期: {a['date']}")
        if a.get("description"):
            desc = a["description"][:300]
            lines.append(f"   摘要: {desc}")
        if a.get("categories"):
            lines.append(f"   分类: {', '.join(a['categories'])}")
        lines.append("")

    return "\n".join(lines)


def fetch_all_news() -> str:
    """从所有配置的源获取、过滤并聚合新闻，返回格式化的文本"""
    all_articles: list[dict] = []

    for feed in FEEDS:
        try:
            feed_type = feed["type"]
            if feed_type == "rss":
                articles = fetch_rss_feed(feed["url"], feed["name"])
            elif feed_type == "cadence_rss":
                articles = fetch_cadence_news()
            elif feed_type == "synopsys_html":
                articles = fetch_synopsys_news()
            elif feed_type == "digitimes_html":
                articles = fetch_digitimes_news()
            else:
                logging.warning(f"未知的 feed 类型: {feed_type}")
                continue

            relevant = [a for a in articles if is_relevant_article(a)]
            all_articles.extend(relevant)
            logging.info(
                f"[{feed['name']}] 获取 {len(articles)} 篇, "
                f"相关 {len(relevant)} 篇"
            )

        except Exception as e:
            logging.warning(f"[{feed['name']}] 获取失败: {e}", exc_info=True)

    logging.info(f"总计获取相关文章: {len(all_articles)} 篇")

    # 去重（按标题相似度）
    all_articles = _deduplicate_articles(all_articles)

    return format_articles_for_llm(all_articles)


def _deduplicate_articles(articles: list[dict]) -> list[dict]:
    """基于标题的简单去重"""
    seen_titles = set()
    result = []
    for a in articles:
        # 取标题前 50 个字符作为去重键
        key = a["title"][:50].lower().strip()
        if key and key not in seen_titles:
            seen_titles.add(key)
            result.append(a)
    if len(result) < len(articles):
        logging.info(f"去重: {len(articles)} -> {len(result)} 篇")
    return result


def call_llm(system_prompt: str, user_message: str = "") -> str:
    """调用 OpenRouter LLM"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = [{"role": "system", "content": system_prompt}]
    if user_message:
        messages.append({"role": "user", "content": user_message})

    data = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.7,
    }

    logging.info(f"正在调用 LLM ({LLM_MODEL})...")
    for i in range(3):
        resp = None
        try:
            resp = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=120)
            resp.raise_for_status()
            result = resp.json()
            break
        except (requests.ConnectionError, requests.exceptions.JSONDecodeError, ValueError) as e:
            # 记录响应原文的前 1000 字符，便于排查 API 实际返回了什么
            resp_text = resp.text[:1000] if resp is not None else '(请求未完成，无响应)'
            logging.warning(
                f"LLM 请求失败 (第{i+1}次): {type(e).__name__}: {e}\n"
                f"响应原文(前1000字符): {resp_text}"
            )
            if i < 2:
                wait = (i + 1) * 5
                logging.warning(f"{wait}秒后重试...")
                time.sleep(wait)
            else:
                raise
    content = result["choices"][0]["message"]["content"]
    logging.info(f"LLM 返回内容长度: {len(content)} 字符")
    return content


def _source_references_from_news_text(news_text: str) -> list[dict]:
    """从给 LLM 的新闻材料中提取可用于后处理追加的信源信息。"""
    refs: list[dict] = []
    current: dict | None = None
    current_generic_source = ""

    def flush_current():
        nonlocal current
        if current:
            refs.append(current)
            current = None

    for raw_line in news_text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_current()
            continue

        article_match = re.match(r"^\d+\.\s+\[([^\]]+)\](?:\s+\[[^\]]+\])?\s+(.+)$", line)
        if article_match:
            flush_current()
            current = {
                "source": article_match.group(1).strip(),
                "title": article_match.group(2).strip(),
                "link": "",
                "date": "",
                "description": "",
            }
            continue

        if line.startswith("信源:"):
            source_text = line.split(":", 1)[1].strip()
            if current is not None:
                current["source"] = source_text
            else:
                current_generic_source = source_text
                refs.append({
                    "source": source_text,
                    "title": "",
                    "link": "",
                    "date": "",
                    "description": source_text,
                })
            continue

        if current is None:
            continue

        if line.startswith("链接:"):
            current["link"] = line.split(":", 1)[1].strip()
        elif line.startswith("日期:"):
            current["date"] = line.split(":", 1)[1].strip()
        elif line.startswith("摘要:"):
            current["description"] = line.split(":", 1)[1].strip()
        elif line.startswith("分类:"):
            current["description"] = f"{current.get('description', '')} {line}".strip()
        elif line.startswith("聚合源:"):
            current["aggregator_source"] = line.split(":", 1)[1].strip()

    flush_current()

    if current_generic_source and not any(ref.get("source") == current_generic_source for ref in refs):
        refs.append({
            "source": current_generic_source,
            "title": "",
            "link": "",
            "date": "",
            "description": current_generic_source,
        })

    return refs


def _match_tokens(text: str) -> set[str]:
    """提取用于来源匹配的强关键词，避免用泛词造成误配。"""
    text = re.sub(r"\*\*|__|`|\[|\]|\(|\)|（来源[:：].*?）|（论文链接[:：].*?）", " ", text)
    common_en = {
        "about", "after", "again", "agent", "agents", "also", "based", "before",
        "chip", "chips", "could", "first", "foundry", "framework", "from",
        "into", "latest", "model", "models", "more", "news", "paper",
        "release", "released", "says", "semiconductor", "system", "systems",
        "that", "this", "update", "updates", "using", "wafer", "with",
    }
    common_zh = {
        "人工智能", "半导体", "晶圆", "制造", "模型", "发布", "更新", "技术",
        "架构", "框架", "应用", "相关", "最新", "动态", "系统", "工具",
        "平台", "能力", "优化", "提升", "设计", "智能", "行业",
    }
    tokens = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]{3,}", text.lower()):
        if token not in common_en:
            tokens.add(token)
    for chunk in re.findall(r"[\u4e00-\u9fff]{3,}", text):
        if chunk not in common_zh:
            tokens.add(chunk[:14])
    return tokens


def _source_match_score(content_line: str, ref: dict) -> int:
    line_tokens = _match_tokens(content_line)
    title_tokens = _match_tokens(ref.get("title", ""))
    description_tokens = _match_tokens(ref.get("description", ""))
    if not line_tokens or not title_tokens:
        return 0

    title_overlap = line_tokens & title_tokens
    if not title_overlap:
        return 0

    description_overlap = line_tokens & description_tokens
    score = len(title_overlap) * 10 + min(len(description_overlap), 5)
    title = ref.get("title", "")
    if title and (title.lower() in content_line.lower() or content_line.lower() in title.lower()):
        score += 20
    return score


def _is_paper_source(ref: dict) -> bool:
    link = ref.get("link", "").lower()
    source = ref.get("source", "").lower()

    if "x.com/" in link or "twitter.com/" in link:
        return False

    paper_link_markers = (
        "arxiv.org", "openreview.net", "doi.org",
        "biorxiv.org", "medrxiv.org", "ssrn.com", ".pdf",
    )
    if any(marker in link for marker in paper_link_markers):
        return True

    paper_source_markers = ("arxiv", "openreview", "biorxiv", "medrxiv", "ssrn", "doi")
    return any(marker in source for marker in paper_source_markers)


def _source_suffix(ref: dict) -> str:
    link = ref.get("link", "").strip()
    source = ref.get("source", "").strip()
    description = ref.get("description", "").strip()

    if link:
        if _is_paper_source(ref):
            return f"（论文链接：{link}）"
        return f"（来源：[{source or '原文'}]({link})）"

    return f"（来源：{source or description or '信源未提供链接'}）"


def append_sources_to_email_content(email_content: str, news_text: str) -> str:
    """不调用 AI，按新闻材料为正文中的新闻条目追加来源。"""
    refs = _source_references_from_news_text(news_text)
    if not refs:
        logging.warning("未能从新闻材料中提取信源，跳过来源追加")
        return email_content

    output_lines = []
    in_trend_section = False
    appended_count = 0

    for line in email_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_trend_section = "趋势" in stripped

        is_bullet = stripped.startswith("* ") or stripped.startswith("- ")
        has_source = "（来源：" in stripped or "（论文链接：" in stripped

        if is_bullet and not in_trend_section and not has_source:
            best_ref = None
            best_score = 0
            for ref in refs:
                score = _source_match_score(stripped, ref)
                if score > best_score:
                    best_ref = ref
                    best_score = score

            if best_ref and best_score >= 2:
                line = f"{line}{_source_suffix(best_ref)}"
                appended_count += 1

        output_lines.append(line)

    logging.info(f"已通过脚本为 {appended_count} 条正文信息追加来源")
    return "\n".join(output_lines)



def generate_email_content(news_text: str) -> str:
    """生成邮件正文（约1500-2000字总结 + 趋势洞察）"""
    system_prompt = (
        "你是一位大语言模型与半导体领域的专家。以下是最近一周（7天）内更新的AI与半导体领域新闻。\n"
        "请根据这些新闻内容总结，以电子邮件的形式输出约1500-2000字的总结结果以及两百字左右的趋势洞察。\n\n"
        "趋势洞察部分请务必使用分点、换行格式（每条趋势以 * 开头，换行分隔）。\n"
        "不要在正文中自行添加来源、链接、参考资料或脚注；来源会由程序在生成后自动追加。\n"
        "注意：只输出电子邮件正文的内容，不要输出任何其他信息，不需要开场白，不需要问候语，直接输出内容。\n\n"
        "请分别覆盖以下两个主题：\n\n"
        "1. AI 智能体架构（Agent Architecture）相关动态\n"
        "   在此主题下，请重点关注：\n"
        "   - 类似 Open Claw 的智能体架构设计、多智能体协作、自主决策\n"
        "   - 提示词工程（Prompt Engineering）：最佳实践、自动优化、DSPy 等\n"
        "   - Context Engineering：上下文管理、记忆机制、长上下文利用\n"
        "   - Agent 框架与工具：tool use、function calling、MCP 协议、编排（orchestration）\n"
        "   - RAG、推理链、自主Agent 等前沿动态\n\n"
        "2. 半导体晶圆制造（Semiconductor Wafer Manufacturing）相关动态\n"
        "   在此主题下，请重点关注，内容偏向 Foundry 代工与晶圆制造视角：\n"
        "   - AI for 智能制造与晶圆代工：良率优化、缺陷检测、过程控制、数字孪生\n"
        "   - 先进制程进展（N2、N1.4、A14、GAA、CFET 等）与 AI 辅助工艺开发\n"
        "   - Foundry 动态（TSMC、Samsung Foundry、Intel Foundry、GlobalFoundries 等）\n"
        "   - AI for EDA 辅助设计与集成电路设计：AI 辅助布局布线、时序收敛、功耗优化\n"
        "   - EDA 工具 AI 化（Synopsys DSO.ai、Cadence Cerebrus 等）\n"
        "   - AI for Science 相关：AI 驱动的材料科学、计算化学在半导体中的应用\n"
        "   - 先进封装与异构集成（CoWoS、3D-IC、Chiplet 等）\n\n"
        '输出示例：\n'
        '## AI 智能体架构\n\n'
        '### 一、Agent 架构与框架演进\n\n'
        '* **Open Claw 架构最新进展：** ...\n'
        '* **多智能体协作框架：** ...\n\n'
        '### 二、提示词工程与 Context Engineering\n\n'
        '* **提示词自动优化技术：** ...\n'
        '* **长上下文管理突破：** ...\n\n'
        '## 半导体晶圆制造\n\n'
        '### 三、先进制程与 Foundry 动态\n\n'
        '* **TSMC N2P 最新进展：** ...\n'
        '* **EUV 技术突破：** ...\n\n'
        '### 四、AI for EDA 与 IC 设计\n\n'
        '* **Synopsys DSO.ai 新功能：** ...\n'
        '* **Cadence Cerebrus 智能优化：** ...\n\n'
        '### 五、AI for 智能制造与晶圆代工\n\n'
        '* **数字孪生在晶圆厂的应用：** ...\n'
        '* **AI 驱动的良率优化：** ...\n\n'
        '---\n\n'
        '## 趋势洞察\n\n'
        '本期动态映射出以下核心趋势：\n\n'
        '* **趋势一：** ...\n'
        '* **趋势二：** ...\n'
    )
    return call_llm(system_prompt, news_text)


def generate_email_subject(email_body: str, news_date: str) -> str:
    """生成邮件主题"""
    system_prompt = (
        "你是一位大语言模型与半导体领域的专家。以下是发给用户的每周AI与半导体新闻邮件正文。"
        f"请根据这些内容生成邮件主题，格式为：AI与半导体周报 {news_date}：<关键新闻摘要>。"
        "注意：只输出邮件主题，不要输出任何其他信息。"
    )
    return call_llm(system_prompt, email_body)


def sanitize_email_subject(subject: str) -> str:
    """清理 LLM 生成的邮件主题，去除冒号和下划线。"""
    subject = subject.strip().strip('"').strip("'")
    subject = subject.replace("：", " ").replace(":", " ").replace("_", " ")
    subject = re.sub(r"\s+", " ", subject)
    return subject.strip()




def generate_weekly_email() -> tuple[str, str, str] | None:
    """生成本周邮件标题、正文和新闻日期。"""
    validate_generation_config()
    today_str = datetime.now().strftime("%Y-%m-%d")
    checkpoint = load_checkpoint()

    # 1. 获取 AI 日报源（Juya + AI HOT 并列）
    news_text_parts: list[str] = []

    # 1a. Juya AI Daily RSS
    juya_checkpoint = get_checkpoint_step(checkpoint, "juya_news")
    if juya_checkpoint is not None:
        juya_news = juya_checkpoint.get("juya_news", "")
        news_date = juya_checkpoint.get("news_date", today_str)
        logging.info("从 checkpoint 恢复 Juya RSS 内容")
    else:
        try:
            raw_html = fetch_rss()
            juya_news, news_date = extract_weekly_news(raw_html)
            if juya_news:
                logging.info(f"Juya RSS 获取成功，内容长度: {len(juya_news)} 字符")
            else:
                logging.warning("Juya RSS 未提取到最近7天新闻")
                news_date = today_str
        except Exception as e:
            logging.warning(f"Juya RSS 获取失败: {e}")
            juya_news = ""
            news_date = today_str
        save_checkpoint_step("juya_news", {
            "juya_news": juya_news,
            "news_date": news_date,
        })

    if juya_news:
        news_text_parts.append(juya_news)

    # 1b. AI HOT 每日精选（与 Juya 并列的 AI 行业动态源）
    aihot_checkpoint = get_checkpoint_step(checkpoint, "aihot_news")
    if aihot_checkpoint is not None:
        aihot_news = aihot_checkpoint.get("aihot_news", "")
        logging.info("从 checkpoint 恢复 AI HOT 内容")
    else:
        try:
            aihot_news = fetch_aihot_news()
            if aihot_news:
                logging.info(f"AI HOT 获取成功，内容长度: {len(aihot_news)} 字符")
            else:
                logging.warning("AI HOT 未获取到内容")
        except Exception as e:
            logging.warning(f"AI HOT 获取失败: {e}")
            aihot_news = ""
        save_checkpoint_step("aihot_news", {"aihot_news": aihot_news})

    if aihot_news:
        news_text_parts.append(
            "=== 以下来自 AI HOT 每日精选（最近7天） ===\n\n"
            f"{aihot_news}"
        )

    # 2. 获取多源半导体与AI新闻
    multi_source_checkpoint = get_checkpoint_step(checkpoint, "multi_source_news")
    if multi_source_checkpoint is not None:
        multi_source_news = multi_source_checkpoint.get("multi_source_news", "")
        logging.info("从 checkpoint 恢复多源新闻内容")
    else:
        logging.info("=" * 40)
        logging.info("开始获取多源半导体与AI新闻...")
        multi_source_news = fetch_all_news()
        if multi_source_news:
            logging.info(f"多源新闻获取成功，内容长度: {len(multi_source_news)} 字符")
        else:
            logging.warning("多源新闻获取为空")
        save_checkpoint_step("multi_source_news", {
            "multi_source_news": multi_source_news,
        })

    if multi_source_news:
        news_text_parts.append(
            "=== 以下来自多源半导体与AI新闻采集（最近7天） ===\n\n"
            f"{multi_source_news}"
        )

    # 3. 合并所有内容
    combined_checkpoint = get_checkpoint_step(checkpoint, "combined_news_text")
    if combined_checkpoint is not None:
        combined_news_text = combined_checkpoint.get("combined_news_text", "")
        news_date = combined_checkpoint.get("news_date", news_date)
        logging.info("从 checkpoint 恢复合并新闻内容")
    else:
        combined_news_text = "\n\n".join(news_text_parts)
        save_checkpoint_step("combined_news_text", {
            "combined_news_text": combined_news_text,
            "news_date": news_date,
        })

    if not combined_news_text.strip():
        logging.warning("所有新闻源均未获取到内容，任务终止")
        return None

    logging.info(f"合并总内容长度: {len(combined_news_text)} 字符")

    # 4. 生成邮件正文
    raw_content_checkpoint = get_checkpoint_step(checkpoint, "email_content_raw")
    if raw_content_checkpoint is not None:
        email_content_raw = raw_content_checkpoint.get("email_content_raw", "")
        logging.info("从 checkpoint 恢复 LLM 邮件正文")
    else:
        logging.info("开始生成邮件正文...")
        email_content_raw = generate_email_content(combined_news_text)
        save_checkpoint_step("email_content_raw", {
            "email_content_raw": email_content_raw,
        })

    sourced_content_checkpoint = get_checkpoint_step(checkpoint, "email_content_with_sources")
    if sourced_content_checkpoint is not None:
        email_content = sourced_content_checkpoint.get("email_content", "")
        logging.info("从 checkpoint 恢复已追加来源的邮件正文")
    else:
        email_content = append_sources_to_email_content(email_content_raw, combined_news_text)
        save_checkpoint_step("email_content_with_sources", {
            "email_content": email_content,
        })
    logging.info(f"邮件正文:\n{email_content}")

    # 5. 生成邮件主题
    title_checkpoint = get_checkpoint_step(checkpoint, "email_title")
    if title_checkpoint is not None:
        email_title = title_checkpoint.get("email_title", "")
        logging.info("从 checkpoint 恢复邮件主题")
    else:
        logging.info("开始生成邮件主题...")
        email_title = sanitize_email_subject(generate_email_subject(email_content, news_date))
        save_checkpoint_step("email_title", {
            "email_title": email_title,
            "news_date": news_date,
        })
    logging.info(f"邮件主题: {email_title}")

    return email_title, email_content, news_date
