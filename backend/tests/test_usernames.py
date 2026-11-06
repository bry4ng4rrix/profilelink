import pytest

from app.core.usernames import RESERVED_USERNAMES, normalize_username, username_candidates
from tests.conftest import create_va


def first(first_name: str, last_name: str, count: int = 1) -> list[str]:
    candidates = username_candidates(first_name, last_name)
    return [next(candidates) for _ in range(count)]


def test_first_name_comes_first_then_full_name_then_a_number():
    assert first("Bryan", "Rakoto", 4) == [
        "bryan",
        "bryan-rakoto",
        "bryan-rakoto-2",
        "bryan-rakoto-3",
    ]


@pytest.mark.parametrize(
    "first_name,last_name,expected",
    [
        ("Léa", "Andrïa", "lea"),
        ("Jean-Luc", "Rabe", "jean-luc"),
        ("Jean Luc", "Rabe", "jean-luc"),
        ("  Marie ", "Rabe", "marie"),
        ("O'Neil", "Rabe", "o-neil"),
        ("NIRINA", "Rabe", "nirina"),
        ("Jo", "Rakoto", "jo-rakoto"),
        ("Admin", "Rakoto", "admin-rakoto"),
        ("Login", "Rabe", "login-rabe"),
        ("Dashboard", "Rabe", "dashboard-rabe"),
    ],
)
def test_names_become_clean_addresses(first_name, last_name, expected):
    assert first(first_name, last_name) == [expected]


def test_names_without_latin_letters_still_get_an_address():
    assert first("Анна", "Иванова") == ["va-2"]


def test_very_long_names_stay_within_the_limit():
    candidates = first("A" * 80, "B" * 80, 5)

    assert all(len(name) <= 30 for name in candidates)
    assert all(normalize_username(name) == name for name in candidates)


@pytest.mark.parametrize("reserved", sorted(RESERVED_USERNAMES))
def test_reserved_names_are_never_generated(reserved):
    assert reserved not in first(reserved, "Rakoto", 5)


async def test_homonyms_get_distinct_addresses(admin):
    urls = [(await create_va(admin))["public_url"] for _ in range(3)]

    assert [url.rsplit("/", 1)[1] for url in urls] == ["bryan", "bryan-rakoto", "bryan-rakoto-2"]


async def test_address_stays_the_same_when_the_name_is_corrected(admin):
    va = await create_va(admin)

    response = await admin.put(
        f"/api/v1/admin/vas/{va['id']}",
        json={
            "first_name": "Brian",
            "last_name": "Rakoto",
            "age": 27,
            "instagram_url": va["instagram_url"],
        },
    )

    assert response.json()["first_name"] == "Brian"
    assert response.json()["username"] == "bryan"
