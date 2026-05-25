"""
Tests for the character builder feature:
- build_character_description() correctness
- Graceful handling of missing/None fields
- Story generation endpoint accepts and stores hero_character
"""

import json
import pytest
from prompt_manager import build_character_description


# ── build_character_description tests ─────────────────────────────────

class TestBuildCharacterDescription:
    """Unit tests for build_character_description()."""

    def test_full_character(self):
        char = {
            'skin_tone': 'brown',
            'hair_style': 'short curly',
            'hair_color': 'black',
            'outfit': 'superhero',
            'accessory': 'shield',
            'medical_detail': 'arm cast',
        }
        desc = build_character_description(char)
        assert 'warm brown skin' in desc
        assert 'short curly black hair' in desc
        assert 'blue superhero suit' in desc
        assert 'glowing shield' in desc
        assert 'arm cast decorated with star stickers' in desc
        assert desc.startswith('The hero has ')
        assert desc.endswith('.')

    def test_skin_tone_only(self):
        desc = build_character_description({'skin_tone': 'light'})
        assert desc == 'The hero has light skin.'

    def test_hair_style_and_color(self):
        desc = build_character_description({'hair_style': 'braids', 'hair_color': 'red'})
        assert 'braids red hair' in desc

    def test_hair_style_only(self):
        desc = build_character_description({'hair_style': 'long straight'})
        assert 'long straight hair' in desc

    def test_hair_color_only(self):
        desc = build_character_description({'hair_color': 'blonde'})
        assert 'blonde hair' in desc

    def test_outfit_descriptions(self):
        for outfit, expected_fragment in [
            ('superhero', 'blue superhero suit'),
            ('astronaut', 'white astronaut suit'),
            ('wizard', 'purple wizard robe'),
            ('explorer', 'green explorer vest'),
        ]:
            desc = build_character_description({'outfit': outfit})
            assert expected_fragment in desc, f"Expected '{expected_fragment}' for outfit='{outfit}'"

    def test_accessory_descriptions(self):
        for acc, expected_fragment in [
            ('cape', 'flowing cape'),
            ('shield', 'glowing shield'),
            ('wand', 'sparkling magic wand'),
            ('backpack', 'adventure backpack'),
        ]:
            desc = build_character_description({'accessory': acc})
            assert expected_fragment in desc

    def test_medical_detail_descriptions(self):
        for med, expected_fragment in [
            ('arm cast', 'arm cast decorated with star stickers'),
            ('eye patch', 'pirate-style eye patch'),
            ('wheelchair', 'speedy, decorated wheelchair'),
            ('head bandana', 'colorful hero bandana'),
        ]:
            desc = build_character_description({'medical_detail': med})
            assert expected_fragment in desc

    def test_medical_none_excluded(self):
        desc = build_character_description({'medical_detail': 'none', 'skin_tone': 'medium'})
        assert 'none' not in desc.lower() or 'skin' in desc
        assert 'proudly' not in desc

    def test_none_input(self):
        assert build_character_description(None) == ''

    def test_empty_dict(self):
        assert build_character_description({}) == ''

    def test_non_dict_input(self):
        assert build_character_description('not a dict') == ''

    def test_all_none_values(self):
        char = {
            'skin_tone': None,
            'hair_style': None,
            'hair_color': None,
            'outfit': None,
            'accessory': None,
            'medical_detail': None,
        }
        assert build_character_description(char) == ''

    def test_unknown_values_fallback(self):
        desc = build_character_description({
            'outfit': 'pirate',
            'accessory': 'sword',
        })
        assert 'pirate outfit' in desc
        assert 'a sword' in desc


# ── Integration: story endpoint accepts hero_character ────────────────

class TestStoryEndpointHeroCharacter:
    """Verify that the generation endpoint stores hero_character in DB."""

    def test_create_story_with_hero_character(self, app):
        import database_v2 as db
        hero_char = {
            'skin_tone': 'medium-light',
            'hair_style': 'long curly',
            'hair_color': 'auburn',
            'outfit': 'wizard',
            'accessory': 'wand',
            'medical_detail': 'head bandana',
        }
        story = db.create_story(
            child_name='Luna', age=7, gender='girl',
            condition='asthma',
            hero_characteristics='brave, creative',
            story_title="Luna's Magic Quest",
            pages=[{'text': 'Page 1', 'imageUrl': None, 'pageNumber': 1}],
            user_id=None,
            hero_character=hero_char,
        )
        assert story is not None
        assert story['heroCharacter'] == hero_char

    def test_create_story_without_hero_character(self, app):
        import database_v2 as db
        story = db.create_story(
            child_name='Max', age=5, gender='boy',
            condition='broken leg',
            hero_characteristics='brave',
            story_title="Max's Adventure",
            pages=[{'text': 'Page 1', 'imageUrl': None, 'pageNumber': 1}],
            user_id=None,
        )
        assert story is not None
        assert story.get('heroCharacter') is None

    def test_create_story_hero_character_persisted(self, app):
        import database_v2 as db
        hero_char = {'skin_tone': 'dark-brown', 'outfit': 'astronaut'}
        story = db.create_story(
            child_name='Zara', age=10, gender='girl',
            condition='diabetes',
            hero_characteristics='determined',
            story_title="Zara's Space Mission",
            pages=[{'text': 'Blast off!', 'imageUrl': None, 'pageNumber': 1}],
            user_id=1,
            hero_character=hero_char,
        )
        assert story is not None
        # get_story now requires user_id for ownership scoping.
        fetched = db.get_story(story['id'], user_id=1)
        assert fetched is not None  # type narrowing for Pylance
        assert fetched['heroCharacter'] == hero_char  # noqa: E501
