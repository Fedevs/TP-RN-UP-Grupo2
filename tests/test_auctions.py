from datetime import datetime, timedelta

from tools import list_active_auctions, save_auction

PS5 = {"name": "PlayStation 5", "category": "consoles", "condition": "used", "details": None}
IPHONE = {"name": "iPhone 13 128GB", "category": "phones", "condition": "used", "details": None}


def draft(title, category, price=100000, days=7):
    return {
        "title": title,
        "description": "Descripción de prueba con el largo suficiente para la publicación.",
        "category": category,
        "starting_price": price,
        "duration_days": days,
    }


def test_saved_auction_is_listed_with_its_data():
    auction_id = save_auction(draft("PlayStation 5 con 2 joysticks", "consoles", 450000), PS5)
    [saved] = list_active_auctions()
    assert saved["id"] == auction_id
    assert saved["product_name"] == "PlayStation 5"
    assert saved["starting_price"] == 450000
    created = datetime.fromisoformat(saved["created_at"])
    assert datetime.fromisoformat(saved["ends_at"]) - created == timedelta(days=7)


def test_finished_auctions_are_not_listed():
    save_auction(draft("Subasta vieja", "consoles"), PS5, now=datetime.now() - timedelta(days=8))
    active_id = save_auction(draft("Subasta nueva", "consoles"), PS5)
    assert [a["id"] for a in list_active_auctions()] == [active_id]


def test_list_filters_by_category_and_orders_by_end():
    later = save_auction(draft("PS5 a 7 días", "consoles", days=7), PS5)
    sooner = save_auction(draft("PS5 a 3 días", "consoles", days=3), PS5)
    save_auction(draft("iPhone 13", "phones"), IPHONE)
    assert [a["id"] for a in list_active_auctions("consoles")] == [sooner, later]
    assert len(list_active_auctions()) == 3


def test_list_is_safe_against_sql_injection():
    save_auction(draft("PS5", "consoles"), PS5)
    assert list_active_auctions("' OR 1=1 --") == []
    assert len(list_active_auctions()) == 1
