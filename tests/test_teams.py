from outlook_reminder.teams import find_teams_url, msteams_uri

JOIN = ("https://teams.microsoft.com/l/meetup-join/19%3ameeting_NjM0%40thread.v2/0"
        "?context=%7b%22Tid%22%3a%2272f9%22%2c%22Oid%22%3a%22a1b2%22%7d")


def test_finds_the_join_link_in_outlooks_meeting_text():
    text = (
        "________________________________________________________________________________\n"
        "Microsoft Teams meeting\nJoin on your computer, mobile app or room device\n"
        f"Click here to join the meeting<{JOIN}>\nMeeting ID: 123 456 789\n"
    )
    assert find_teams_url(text) == JOIN


def test_finds_the_short_meet_link_and_the_new_teams_domain():
    assert find_teams_url("Join: https://teams.microsoft.com/meet/2468?p=abc now") == \
        "https://teams.microsoft.com/meet/2468?p=abc"
    assert find_teams_url("https://teams.cloud.microsoft/meet/2468?p=abc") == \
        "https://teams.cloud.microsoft/meet/2468?p=abc"


def test_other_links_are_not_teams_links():
    assert find_teams_url("Agenda: https://example.com/agenda and https://teams.microsoft.com/") is None
    assert find_teams_url("") is None


def test_the_join_link_opens_in_teams_for_linux_through_msteams():
    assert msteams_uri(JOIN) == "msteams:" + JOIN.removeprefix("https://teams.microsoft.com")
    assert msteams_uri("https://teams.cloud.microsoft/meet/2468?p=abc") == "msteams:/meet/2468?p=abc"
