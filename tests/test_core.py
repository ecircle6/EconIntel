"""核心逻辑冒烟测试（unittest，无网络依赖）。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "generator"))

from app.exporters.site import block_index  # noqa: E402
from app.processors.classify import classify  # noqa: E402
from app.processors.dedup import (  # noqa: E402
    author_surname,
    choose_root,
    normalize_doi,
    normalize_title,
    title_author_key,
)
from app.processors.importance import compute_score, label_for  # noqa: E402
from app.processors.summarize import (  # noqa: E402
    rule_contribution,
    rule_keywords,
    rule_short_title,
)


class TestDedup(unittest.TestCase):
    def test_normalize_doi(self):
        self.assertEqual(normalize_doi(" 10.3386/W12345. "), "10.3386/w12345")
        self.assertIsNone(normalize_doi("not-a-doi"))

    def test_normalize_title(self):
        self.assertEqual(normalize_title("  Monetary Policy,   Inflation! "), "monetary policy inflation")

    def test_author_surname(self):
        self.assertEqual(author_surname("James J. Feigenbaum"), "feigenbaum")
        self.assertEqual(author_surname("Escobar Carias, Michelle"), "escobar carias")  # 逗号格式取逗号前
        self.assertEqual(author_surname("张三"), "张三")

    def test_title_author_key(self):
        k1 = title_author_key("Monetary Policy and Inflation", ["Smith, John"])
        k2 = title_author_key("monetary policy and inflation!!", ["John Smith"])
        # 规范化后一致（姓氏 Smith 统一）
        self.assertEqual(k1.split("|")[1], k2.split("|")[1])

    def test_choose_root_prefers_journal(self):
        from types import SimpleNamespace

        wp = SimpleNamespace(paper_type="working", published_at=datetime(2026, 7, 1), id=1)
        jr = SimpleNamespace(paper_type="journal", published_at=datetime(2026, 8, 1), id=2)
        self.assertEqual(choose_root([wp, jr]).id, 2)
        newer = SimpleNamespace(paper_type="working", published_at=datetime(2026, 8, 10), id=3)
        self.assertEqual(choose_root([wp, newer]).id, 3)


class TestImportance(unittest.TestCase):
    W = {"institution": 25, "citations": 45, "recency": 24, "paper_type": 6}
    TODAY = datetime(2026, 8, 14)

    def test_fresh_hot(self):
        score = compute_score("A", "working", 100, self.TODAY - timedelta(days=3), self.TODAY, self.W)
        self.assertGreaterEqual(score, 80)
        self.assertEqual(label_for(score), "🔥热点")

    def test_old_low(self):
        score = compute_score("C", "working", 0, self.TODAY - timedelta(days=85), self.TODAY, self.W)
        self.assertLess(score, 60)
        self.assertEqual(label_for(score), "📄普通")

    def test_mid_band(self):
        # A 官方机构 + 期刊 + 30 引用 + 近 10 天 → ⭐重要
        score = compute_score("A", "journal", 30, self.TODAY - timedelta(days=10), self.TODAY, self.W)
        self.assertGreaterEqual(score, 60)
        self.assertLess(score, 80)
        self.assertEqual(label_for(score), "⭐重要")

    def test_never_exceeds_100(self):
        score = compute_score("A", "journal", 10**6, self.TODAY, self.TODAY, self.W)
        self.assertLessEqual(score, 100)


class TestClassify(unittest.TestCase):
    def test_macro(self):
        self.assertEqual(classify("Monetary Policy and Inflation Dynamics", "We study the central bank's interest rate policy."), "宏观")

    def test_finance(self):
        self.assertEqual(classify("Asset Pricing with Credit Risk", "We analyze bank lending, bond markets and leverage."), "金融")

    def test_fallback(self):
        self.assertEqual(classify("A Strange Title about Quarks", ""), "其他")


class TestSummarizeRules(unittest.TestCase):
    def test_short_title(self):
        long_title = "The Role of Monetary Policy in Stabilizing Inflation Expectations"
        short = rule_short_title(long_title)
        self.assertLessEqual(len(short), 70)
        self.assertTrue(short.startswith("Role"))  # 前导冠词被去掉
        self.assertLessEqual(len(rule_short_title("Short Title")), 15)

    def test_contribution_first_sentence(self):
        self.assertEqual(rule_contribution("We find large effects. Then we discuss."), "We find large effects.")
        self.assertEqual(rule_contribution(""), "")

    def test_keywords(self):
        kws = rule_keywords("Monetary Policy", "We study inflation, monetary policy, and central bank communication.")
        self.assertIsInstance(kws, list)
        self.assertGreaterEqual(len(kws), 1)


class TestBlocks(unittest.TestCase):
    def test_block_boundaries(self):
        # 90 天窗口 = 3 块：b1 0-29 天、b2 30-59 天、b3 60-89 天（越界归入 b3）
        self.assertEqual(block_index(0, 3), 0)
        self.assertEqual(block_index(29, 3), 0)
        self.assertEqual(block_index(30, 3), 1)
        self.assertEqual(block_index(59, 3), 1)
        self.assertEqual(block_index(60, 3), 2)
        self.assertEqual(block_index(200, 3), 2)
        self.assertEqual(block_index(-1, 3), 0)

    def test_dynamic_window(self):
        # 180 天 → 6 块
        self.assertEqual(block_index(170, 6), 5)


if __name__ == "__main__":
    unittest.main()
