import unittest

from bot import Listing, is_flip_candidate, parse_olx_html


SAMPLE = '''
<html><head><title>iphone 13 - OLX.pl</title></head><body>
<main>
  <div data-cy="l-card">
    <a href="/d/oferta/iphone-13-pro-IDabc123.html"><h6>iPhone 13 Pro 128 GB</h6></a>
    <p data-testid="ad-price">900 zł</p>
    <p data-testid="location-date">Bielsko-Biała - dzisiaj</p>
    <img src="https://img.example/phone.jpg" />
  </div>
  <div data-cy="l-card">
    <a href="/d/oferta/etui-iphone-13-IDdef456.html"><h6>Etui iPhone 13</h6></a>
    <p data-testid="ad-price">20 zł</p>
  </div>
</main>
</body></html>
'''


class ParserTests(unittest.TestCase):
    def test_parse_cards(self):
        listings = parse_olx_html(SAMPLE)
        self.assertEqual(len(listings), 2)
        self.assertEqual(listings[0].title, "iPhone 13 Pro 128 GB")
        self.assertEqual(listings[0].price, "900 zł")
        self.assertEqual(listings[0].listing_id, "IDABC123")
        self.assertEqual(listings[0].image_url, "https://img.example/phone.jpg")

    def test_target_filter(self):
        cfg = {
            "include_title_regex": r"\biphone\s*(11|12|13)\b",
            "exclude_title_words": ["etui", "kabel"],
        }
        good = Listing("1", "iPhone 13 Pro 128 GB", "https://www.olx.pl/a")
        accessory = Listing("2", "Etui iPhone 13", "https://www.olx.pl/b")
        excluded_generation = Listing("3", "iPhone 14 Pro", "https://www.olx.pl/c")
        self.assertTrue(is_flip_candidate(good, cfg))
        self.assertFalse(is_flip_candidate(accessory, cfg))
        self.assertFalse(is_flip_candidate(excluded_generation, cfg))


if __name__ == "__main__":
    unittest.main()
