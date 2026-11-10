"""Browser tests for the shortlist page and its places.json.

The kiosk (blackdiamondlodge/bdh-app-restaurants) puts the shortlist in the URL
hash; phone cameras may percent-encode parts of it before opening the page.

    pip install selenium && python -m unittest discover tests
"""
import functools
import http.server
import json
import pathlib
import re
import socketserver
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLACES = json.loads((ROOT / "places.json").read_text(encoding="utf-8"))["places"]


class PlacesJsonTests(unittest.TestCase):
    def test_well_formed(self):
        self.assertGreater(len(PLACES), 0)
        for code, p in PLACES.items():
            self.assertRegex(code, r"^[0-9a-z]{3}$")
            self.assertTrue(p["n"].strip(), code)
            self.assertRegex(p["p"], r"^[A-Za-z0-9_-]*$", code)


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
        handler.log_message = lambda *a: None
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d/index.html" % cls.server.server_address[1]

        from selenium import webdriver
        options = webdriver.ChromeOptions()
        for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage"):
            options.add_argument(arg)
        cls.driver = webdriver.Chrome(options=options)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        cls.server.shutdown()
        cls.server.server_close()

    def rendered(self, hash_):
        """Open the page with this hash; return [(pin, name, href)]."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        d = self.driver
        d.get("about:blank")
        d.get(self.base + "#" + hash_)
        WebDriverWait(d, 10).until(lambda d: d.find_elements(By.CSS_SELECTOR, "a.place, .empty"))
        return [(a.find_element(By.CLASS_NAME, "pin").text, a.find_element(By.CLASS_NAME, "name").text,
                 a.get_attribute("href")) for a in d.find_elements(By.CSS_SELECTOR, "a.place")]

    def codes(self, n):
        return sorted(PLACES)[:n]

    def assert_places(self, hash_, codes):
        got = self.rendered(hash_)
        self.assertEqual([name for _, name, _ in got], [PLACES[c]["n"] for c in codes])
        self.assertEqual([pin for pin, _, _ in got], [str(i + 1) for i in range(len(codes))])
        for (_, _, href), c in zip(got, codes):
            self.assertIn("query_place_id=" + PLACES[c]["p"], href)

    def test_codes_with_any_separator(self):
        codes = self.codes(3)
        for sep in (",", "|", "%7C", "%7c"):
            with self.subTest(sep=sep):
                self.assert_places(sep.join(codes), codes)

    def test_codes_are_case_insensitive(self):
        codes = self.codes(2)
        self.assert_places(",".join(c.upper() for c in codes), codes)

    def test_unknown_codes_are_skipped_and_numbering_stays_contiguous(self):
        a, b = self.codes(2)
        self.assert_places(f"{a},zz9,{b}", [a, b])

    def test_long_form_items(self):
        for hash_ in ("Caf%C3%A9%20%26%20Bar~ChIJabc_-1", "Caf%C3%A9%20%26%20Bar%7EChIJabc_-1"):
            with self.subTest(hash_=hash_):
                [(pin, name, href)] = self.rendered(hash_)
                self.assertEqual((pin, name), ("1", "Café & Bar"))
                self.assertIn("query_place_id=ChIJabc_-1", href)

    def test_long_form_without_place_id_searches_by_name(self):
        [(_, name, href)] = self.rendered("Fondue%20Stube~")
        self.assertEqual(name, "Fondue Stube")
        self.assertNotIn("query_place_id", href)
        self.assertTrue(re.search(r"query=Fondue(%20|\+)Stube", href), href)

    def test_mixed_codes_and_long_form(self):
        a, b = self.codes(2)
        names = [name for _, name, _ in self.rendered(f"{a},Somewhere~ChIJx,{b}")]
        self.assertEqual(names, [PLACES[a]["n"], "Somewhere", PLACES[b]["n"]])

    def test_empty(self):
        from selenium.webdriver.common.by import By
        for hash_ in ("", "zz9,zz8"):
            with self.subTest(hash_=hash_):
                self.assertEqual(self.rendered(hash_), [])
                self.assertIn("empty", self.driver.find_element(By.ID, "list").text)


if __name__ == "__main__":
    unittest.main()
