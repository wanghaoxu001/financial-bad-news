from financial_bad_news.filters import match_keywords, extract_item_text


def test_match_keywords_basic():
    text = "银行出现系统漏洞，导致大规模盗刷事件"
    keywords = ["漏洞", "诈骗", "盗刷"]
    assert match_keywords(text, keywords) == ["漏洞", "盗刷"]


def test_extract_item_text_concatenates():
    item = {"title": "标题", "description": "描述"}
    assert extract_item_text(item) == "标题。描述"
