"""
Prompt Management Framework
────────────────────────────
Versioned prompt templates with personalization support.
Manages story generation prompts and image prompts.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger('brave_story.prompts')

# ── Prompt version ───────────────────────────────────────────────────
PROMPT_VERSION = '3.0.0'


# ── Character description builder ────────────────────────────────────

SKIN_TONE_LABELS = {
    'light': 'light', 'medium-light': 'medium-light',
    'medium': 'medium', 'medium-brown': 'medium-brown',
    'brown': 'warm brown', 'dark-brown': 'dark brown',
}
OUTFIT_DESCRIPTIONS = {
    'superhero': 'a blue superhero suit with a flowing cape',
    'astronaut': 'a shiny white astronaut suit with a helmet',
    'wizard': 'a purple wizard robe with sparkling stars',
    'explorer': 'a green explorer vest with many pockets',
}
ACCESSORY_DESCRIPTIONS = {
    'cape': 'a flowing cape',
    'shield': 'a glowing shield',
    'wand': 'a sparkling magic wand',
    'backpack': 'a sturdy adventure backpack',
}
MEDICAL_DESCRIPTIONS = {
    'arm cast': 'an arm cast decorated with star stickers',
    'eye patch': 'a cool pirate-style eye patch',
    'wheelchair': 'a speedy, decorated wheelchair',
    'head bandana': 'a colorful hero bandana on their head',
}


def build_character_description(character) -> str:
    """Convert a hero character dict into a natural-language description.

    Returns an empty string if no meaningful fields are present.
    """
    if not character or not isinstance(character, dict):
        return ''

    parts = []

    skin = character.get('skin_tone')
    if skin:
        parts.append(f"{SKIN_TONE_LABELS.get(skin, skin)} skin")

    hair_style = character.get('hair_style')
    hair_color = character.get('hair_color')
    if hair_style and hair_color:
        parts.append(f"{hair_style} {hair_color} hair")
    elif hair_style:
        parts.append(f"{hair_style} hair")
    elif hair_color:
        parts.append(f"{hair_color} hair")

    outfit = character.get('outfit')
    if outfit:
        parts.append(f"wears {OUTFIT_DESCRIPTIONS.get(outfit, f'a {outfit} outfit')}")

    accessory = character.get('accessory')
    if accessory:
        parts.append(f"carries {ACCESSORY_DESCRIPTIONS.get(accessory, f'a {accessory}')}")

    medical = character.get('medical_detail')
    if medical and medical != 'none':
        parts.append(f"proudly wears {MEDICAL_DESCRIPTIONS.get(medical, medical)}")

    if not parts:
        return ''

    desc = 'The hero has ' + ', '.join(parts) + '.'
    return desc


# ── Story generation prompt ──────────────────────────────────────────

def build_story_prompt(child_name: str, age: int, gender: str,
                       condition: str, hero_characteristics: str = '',
                       preferences: Optional[list] = None,
                       story_history: Optional[list] = None,
                       story_length: str = '', tone: str = '',
                       theme: str = '', villain_type: str = '',
                       ending_type: str = '', illustration_style: str = '',
                       reading_level: str = '',
                       character_description: str = '') -> str:
    """
    Build a personalized story generation prompt.
    Incorporates child preferences, story history, and custom settings.
    """

    # Age-adapted instructions (can be overridden by reading_level)
    effective_level = reading_level
    if not effective_level:
        if age <= 4:
            effective_level = 'toddler'
        elif age <= 7:
            effective_level = 'early-reader'
        elif age <= 12:
            effective_level = 'older-child'
        else:
            effective_level = 'teen'

    # Determine page count from story_length setting or default by level
    page_counts = {
        'short': 1,
        'medium': 3,
        'long': 5,
    }
    level_defaults = {
        'toddler': 3,
        'early-reader': 3,
        'older-child': 4,
        'teen': 5,
    }
    num_pages = page_counts.get(story_length, level_defaults.get(effective_level, 3))

    level_instructions = {
        'toddler': (
            f"Generate exactly {num_pages} page(s). "
            "Vocabulary: only the simplest everyday words (no more than 2 syllables). "
            "Sentence length: 6-10 words max per sentence, 2-3 sentences per page. "
            "Tone: joyful, bouncy, and warm - like a parent reading aloud at bedtime. "
            "Use onomatopoeia (whoosh, splat, zoom) and gentle repetition to build rhythm. "
            "Every page must end with a small wonder or a smile."
        ),
        'early-reader': (
            f"Generate exactly {num_pages} page(s). "
            "Vocabulary: common words a 5-7-year-old knows; introduce one new 'magic word' per page. "
            "Sentence length: 10-15 words, 3-4 sentences per page. "
            "Tone: playful and encouraging - the hero always figures things out. "
            "Use dialogue (short, punchy lines) and at least one funny moment. "
            "Each page should end with a sense of momentum - what happens next?"
        ),
        'older-child': (
            f"Generate exactly {num_pages} page(s). "
            "Vocabulary: age-appropriate with vivid descriptive language and metaphors. "
            "Sentence length: varied (short for action, longer for feeling), 4-6 sentences per page. "
            "Tone: adventurous and emotionally resonant - the hero feels real doubt then real triumph. "
            "Include natural-sounding dialogue that reveals character. "
            "Build tension across pages and release it in the final page."
        ),
        'teen': (
            f"Generate exactly {num_pages} page(s). "
            "Vocabulary: rich and nuanced; include internal monologue and self-reflection. "
            "Sentence length: fluid and literary, 5-8 sentences per page. "
            "Tone: honest and motivational - acknowledge the hard parts, then show resilience. "
            "Include meaningful dialogue, a clear character arc, and a theme that resonates beyond the story. "
            "The ending should feel earned, not just happy."
        ),
    }
    age_instructions = level_instructions.get(effective_level, level_instructions['early-reader'])

    # Hero characteristics block
    traits_block = ''
    if hero_characteristics:
        traits_block = f"""
HERO CHARACTERISTICS:
The hero {child_name} must consistently display these personality traits: {hero_characteristics}.
These traits should:
- Shape the hero's decisions and actions throughout the story
- Be demonstrated through specific moments and dialogue
- Connect meaningfully to how they overcome their medical challenge
- Provide moral lessons and inspirational messaging
"""

    # Personalization block (based on learned preferences)
    personalization_block = ''
    if preferences:
        liked_themes = [p['preference_value'] for p in preferences
                       if p['preference_type'] == 'theme' and p.get('total_weight', 0) > 0]
        liked_characters = [p['preference_value'] for p in preferences
                           if p['preference_type'] == 'character_type' and p.get('total_weight', 0) > 0]
        liked_settings = [p['preference_value'] for p in preferences
                         if p['preference_type'] == 'setting' and p.get('total_weight', 0) > 0]

        parts = []
        if liked_themes:
            parts.append(f"- Themes this child enjoys: {', '.join(liked_themes[:5])}")
        if liked_characters:
            parts.append(f"- Character types they like: {', '.join(liked_characters[:5])}")
        if liked_settings:
            parts.append(f"- Settings they prefer: {', '.join(liked_settings[:5])}")

        if parts:
            personalization_block = (
                "\nPERSONALIZATION (learned from previous stories):\n"
                + '\n'.join(parts) +
                "\nTry to incorporate these preferences while keeping the story fresh and unique.\n"
            )

    # History awareness
    history_block = ''
    if story_history and len(story_history) > 0:
        prev_titles = [h.get('story_title', '') for h in story_history[:5] if h.get('story_title')]
        if prev_titles:
            history_block = f"""
STORY HISTORY:
This child has previously enjoyed these stories: {', '.join(prev_titles)}.
Create something NEW and different - avoid repeating the same plot or theme.
"""

    # Custom settings block
    settings_block = ''
    settings_parts = []
    if tone:
        tone_map = {
            'funny': 'Make the story funny and humorous with silly moments and jokes.',
            'adventurous': 'Make the story action-packed and exciting with an adventurous tone.',
            'calming': 'Make the story calm, soothing, and gentle - perfect for bedtime.',
            'educational': 'Include educational elements and fun facts woven into the narrative.',
        }
        settings_parts.append(tone_map.get(tone, f'Use a {tone} tone throughout.'))
    if theme:
        theme_map = {
            'superhero': 'Set in a superhero universe with capes, powers, and a heroic mission.',
            'space': 'Set in outer space with planets, stars, rockets, and alien friends.',
            'underwater': 'Set in an underwater world with coral reefs, friendly sea creatures, and hidden treasures.',
            'jungle': 'Set in a lush jungle with exotic animals, vines, and ancient mysteries.',
            'fairy-tale': 'Set in a magical fairy-tale kingdom with castles, enchanted forests, and magical creatures.',
            'dinosaur': 'Set in a prehistoric dinosaur world with friendly dinosaurs and volcanic landscapes.',
        }
        settings_parts.append(theme_map.get(theme, f'Set the story in a {theme} world.'))
    if villain_type:
        villain_map = {
            'monster': 'Portray the medical challenge as a silly, non-scary monster that the hero defeats.',
            'storm': 'Portray the medical challenge as a storm that the hero learns to weather and calm.',
            'puzzle': 'Portray the medical challenge as an exciting puzzle or riddle the hero cleverly solves.',
            'shadow': 'Portray the medical challenge as a shadow that the hero bravely shines light upon.',
        }
        settings_parts.append(villain_map.get(villain_type, f'The challenge appears as {villain_type}.'))
    if ending_type:
        ending_map = {
            'triumphant': 'End with a triumphant, celebratory victory.',
            'peaceful': 'End with a peaceful, serene, and heartwarming resolution.',
            'cliffhanger': 'End with an exciting cliffhanger that teases a future adventure.',
        }
        settings_parts.append(ending_map.get(ending_type, f'End with a {ending_type} ending.'))
    if illustration_style:
        style_map = {
            'ghibli': 'Describe image prompts as soft Studio Ghibli watercolor-style paintings.',
            'spider-punk': 'Describe image prompts as bold Spider-Verse comic-book panel illustrations.',
            'cartoon': 'Describe image prompts as bright cartoon-style illustrations.',
            'watercolor': 'Describe image prompts as soft watercolor-style paintings.',
            'comic-book': 'Describe image prompts as bold comic-book panel illustrations.',
            'pixel-art': 'Describe image prompts as retro pixel-art style illustrations.',
        }
        settings_parts.append(style_map.get(illustration_style.strip().lower(), f'Use {illustration_style} illustration style.'))
    if settings_parts:
        settings_block = '\nCUSTOM SETTINGS:\n' + '\n'.join(f'- {p}' for p in settings_parts) + '\n'

    # Character appearance block
    character_block = ''
    if character_description:
        character_block = f"""
HERO VISUAL APPEARANCE (for illustrator only — NEVER mention in story text):
{character_description}

CRITICAL RULES for using this appearance info:
- Do NOT describe the hero's skin tone, hair, outfit, or physical features in the "text" field of any page.
- The story text must treat the hero as a person with a name and personality — not a visual description.
- Never open a page with phrases like "{child_name}, a [gender] with [skin] skin and [hair] hair..." — this is forbidden.
- Include these appearance details ONLY inside each page's "imagePrompt" field so illustrations stay consistent.
"""

    # Narrative arc guidance keyed by page count
    arc_guides = {
        1: "Single page: open with the hero facing a challenge, and close with them overcoming it joyfully.",
        2: "Page 1 - introduce the hero and the challenge. Page 2 - the hero finds their strength and triumphs.",
        3: "Page 1 - introduce the hero and their world. Page 2 - the challenge appears and the hero faces a hard moment. Page 3 - the hero overcomes it and celebrates.",
        4: "Page 1 - introduce hero and world. Page 2 - the challenge appears. Page 3 - a setback then a breakthrough moment. Page 4 - triumphant resolution and celebration.",
        5: "Page 1 - hero's everyday world. Page 2 - the challenge arrives unexpectedly. Page 3 - first attempt fails or feels overwhelming. Page 4 - hero discovers their inner strength/superpower. Page 5 - glorious victory, reflection, and hope.",
    }
    arc_guide = arc_guides.get(num_pages, arc_guides[3])

    # Main prompt
    prompt = f"""You are an award-winning children's book author and pediatric storytelling specialist. \
Your stories are used in hospitals and therapy centers worldwide to help children feel brave, \
understood, and hopeful about their medical journeys.

MISSION:
Write a deeply personalized, emotionally resonant children's story for {child_name}, \
a {age}-year-old {gender} who has {condition}. \
The story must make {child_name} the undisputed hero - brave, clever, and full of heart.

AGE & READING LEVEL:
{age_instructions}

NARRATIVE STRUCTURE ({num_pages} page{"s" if num_pages != 1 else ""}):
{arc_guide}

MEDICAL FRAMING (critical):
- Clearly and gently name the condition using its clinical name: "{condition}" at least once in the story text.
- Reframe {condition} as the SOURCE of {child_name}'s unique superpower or gift - not a limitation.
- The condition gives the hero a special ability no one else has (e.g., heightened senses, magical energy, a special bond with creatures, etc.).
- Treatment or care routines become empowering rituals, not burdens (e.g., medicine = a courage potion).
- Use child-friendly language around the clinical name so it feels normal, understandable, and not scary.
- Show one specific moment where the condition directly enables the hero to succeed where others could not.
- Show a clear emotional arc from fear/worry to confidence, where {child_name} learns they can face and overcome challenges related to {condition}.
{traits_block}{character_block}{personalization_block}{history_block}{settings_block}
STORYTELLING RULES:
- Every page must move the plot forward - no filler pages.
- Include at least one moment of genuine emotional warmth (a hug, a kind word, a proud smile).
- The hero solves their own problem - they are never rescued passively.
- Use sensory details: what does the hero see, hear, and feel?
- Introduce {condition} early in the story and keep it meaningfully connected to the hero's journey across the whole story.
- The final page must leave the reader feeling proud of {child_name}.

CONTENT SAFETY (non-negotiable):
- Zero violence, death, fear, or hopeless moments.
- No graphic or frightening medical descriptions; clinical naming is allowed only in reassuring, age-appropriate language.
- No stigmatizing language around the condition.
- All adults and friends are unconditionally supportive.
- Every page ends on a note of possibility or joy.

IMAGE PROMPT RULES (for the illustrator):
- Each imagePrompt must be a self-contained scene description (50-80 words).
- Describe the exact moment happening on that page - not a generic scene.
- Always include: character appearance, action/pose, setting, mood, lighting, and art style.
- Use the character description consistently on every page.
- Never include text, words, or letters in image prompts.
- End every imagePrompt with: "Children's storybook illustration, warm and magical, no text."

Return ONLY valid JSON - no markdown, no explanation, no extra keys:
{{
  "title": "A creative, memorable story title (5-8 words)",
  "theme": "one of: adventure | friendship | discovery | courage | magic | healing | wonder",
  "pages": [
    {{
      "text": "The full story text for this page, written for the child.",
      "imagePrompt": "A vivid, detailed scene description for the illustrator. Include character, action, setting, lighting, mood, and art style. No text in image. Children's storybook illustration, warm and magical, no text."
    }}
  ]
}}
"""
    logger.info(f'Built story prompt v{PROMPT_VERSION} for {child_name} (age {age})')
    return prompt


# ── Ghibli style system prompt ───────────────────────────────────────

# CartoonCare Visual Story Engine — Studio Ghibli art style definition.
# Applied to every image prompt. Sections map to the system template:
#   STYLE_PREAMBLE  → Sections 1–2 (medium, color, lighting, anatomy)
#   MEDICAL_RULES   → Section 4 (medical item softening)
#   EXCLUSIONS      → Sections 1 & 4 (forbidden elements)

_GHIBLI_STYLE_PREAMBLE = (
    "Studio Ghibli cel animation style, 2004-2010 era (Howl's Moving Castle through Ponyo aesthetic). "
    "Hand-painted watercolor background with soft brushstroke texture. "
    "Flat cel-shaded character coloring, maximum 2 tones per surface — base color plus one warm shadow tone. "
    "Clean confident black outlines of consistent medium weight; thicker at silhouette edges, thinner for interior detail. "
    "Warm earth-grounded color palette — pigment-on-paper feel, never digital neon. "
    "Shadows are always warm-toned (darker warm hue of base color), never cool gray or blue-gray. "
    "Soft ambient diffused natural light as if on an overcast day or under dappled tree shade. "
    "No harsh directional shadows, no dramatic chiaroscuro, no rim lighting, no lens flare, no bloom. "
    "Character proportions: large round head (1:2 to 1:3 head-to-body ratio), high forehead, "
    "soft circular face, round puffy cheeks, stubby short limbs, small mitten-like hands (fingers suggested not articulated), "
    "round torso with no waist or muscle definition — silhouette soft and blobby like a plush toy. "
    "Facial features: large round eyes with dark pupil, single white highlight dot top-left, thin simple eyebrows; "
    "nose is a tiny dot or small soft bump; mouth is a small simple shape; no defined lips. "
    "Hair rendered as grouped soft rounded clumps, 2 tones, natural volume, no shine streaks. "
    "Background softer and less detailed than foreground characters (painterly depth separation). "
    "Traditional hand-animated film frame quality — not a digital painting, not a photograph."
)

_GHIBLI_MEDICAL_SOFTENING = (
    "Any bandages or casts are decorated with colorful stickers and stars. "
    "Any stethoscope is a fun color (teal, coral, or lavender). "
    "Any medicine is depicted as small colorful candy-like shapes in a friendly container. "
    "Any IV drip is simplified to a small friendly bag with a smiley face, thin simple line, no visible needle entry. "
    "Any hospital setting uses warm colors, rounded furniture, natural light, plants, and artwork on walls. "
    "The child always appears brave, curious, or calm — never terrified or in visible pain. "
    "A friendly companion (animal or kind adult) is present in any medical scene."
)

_GHIBLI_EXCLUSIONS = (
    "Full-bleed edge-to-edge composition. NO border, NO white margin, NO paper edges, "
    "NO frame, NO padding, NO matting — the artwork must fill the entire canvas. "
    "NO photorealistic rendering or textures. "
    "NO 3D modeling, ray tracing, or volumetric lighting. "
    "NO lens effects (bokeh, chromatic aberration, vignetting). "
    "NO visible text, watermarks, letters, numbers, or words anywhere in the image. "
    "NO sharp anime features (pointed chin, giant sparkly eyes, tiny nose bridge, exaggerated proportions). "
    "Friendly, warm, child-safe imagery only — gentle and reassuring throughout."
)

# ── Spider-Verse style ───────────────────────────────────────────────
# Sony 'Spider-Man: Into/Across the Spider-Verse' film aesthetic — 3D
# modeled but rendered through 2D comic-print techniques: CMYK halftone,
# chromatic aberration, hand-inked outlines, neon rim lighting.

_SPIDERVERSE_STYLE_PREAMBLE = (
    "Authentic still frame from the film 'Spider-Man: Into the Spider-Verse'. "
    "This is a SCREEN-PRINTED COMIC look — ink on paper, not a clean digital render. "
    "ABSOLUTE MUST-HAVES, in priority order: "
    "(1) HEAVY BLACK HAND-INKED OUTLINES — thick, chunky, bold comic ink around every shape; "
    "the linework is the most important feature; never thin, never smooth digital lines. "
    "(2) HEAVY CHROMATIC ABERRATION — red and cyan color channels visibly offset and misaligned "
    "along every edge, like a misprinted comic; the colors deliberately do not line up perfectly. "
    "(3) BIG VISIBLE HALFTONE DOTS — you can clearly see the individual printed Ben-Day dots in "
    "every shadow, gradient, and flat color area. "
    "(4) NEON RIM LIGHT in magenta or cyan outlining the character's silhouette. "
    "(5) FLAT CEL-SHADED color — hard-edged posterized shadow shapes, zero soft blending. "
    "Reinforce: thick black ink contours + offset red/cyan misregistration + coarse halftone dots are "
    "the three features that define this style — they must be obvious at a glance. "
    "Hyper-saturated clashing colors. "
    "Warm child-friendly proportions: large round head, soft rounded face, big simple eyes, "
    "stubby limbs — a young kid hero, never a sharp adult build."
)

_SPIDERVERSE_MEDICAL_SOFTENING = (
    "Bandages or casts are bold comic shapes covered in stickers, stars, and marker doodles. "
    "Any stethoscope is a fun neon color with a halftone-dotted disc. "
    "Medicine is small glowing candy-like power-up shapes in a friendly container. "
    "Any IV is a small friendly glowing pouch with a smiley face, thin clean line, no visible needle. "
    "Hospital settings become vibrant stylized comic backdrops — warm saturated colors, rounded furniture, "
    "halftone walls. The child hero always looks brave, determined, or joyful — never scared or in pain. "
    "A friendly companion (animal sidekick or kind adult) is present, drawn in the same comic style."
)

_SPIDERVERSE_EXCLUSIONS = (
    "NOT a smooth clean digital illustration. NOT soft airbrushed rendering. "
    "NOT thin delicate linework — the ink must be THICK and BLACK. "
    "NOT perfectly-aligned colors — the red/cyan offset must be visible. "
    "NOT smooth Pixar/Disney 3D. NOT glossy anime eyes. NOT photorealistic. "
    "NO readable text, letters, or numbers. "
    "Friendly, warm, child-safe imagery only. "
    "NO cluttered background — ONE clear focal point. "
    "Full-bleed, no borders or frames."
)


# ── Style preset registry ────────────────────────────────────────────
#
# Each preset owns everything style-specific: visual preamble, medical
# softening rules, exclusions, background block, mood, character archetype
# templates (per gender), proportions sentence, expression block, and a
# non-medical companion-creature block.

_GHIBLI_ARCHETYPES = {
    'male': (
        "short tousled dark-brown hair rendered as soft rounded clumps, "
        "wearing a loose oversized muted-yellow or soft-green t-shirt and dark-brown short pants"
    ),
    'female': (
        "voluminous messy warm red-orange hair radiating outward rendered as soft rounded clumps, "
        "wearing a simple A-line dress in cherry red or soft pink with white bloomers peeking at hem"
    ),
    'neutral': (
        "warm brown tousled hair rendered as soft rounded clumps, "
        "wearing a cozy muted-colored outfit"
    ),
}

_SPIDERVERSE_ARCHETYPES = {
    'male': (
        "short curly dark hair with energy, "
        "wearing a hooded sneaker-culture hero outfit — bright graphic jacket over a tee, "
        "in clashing saturated colors with neon accent piping"
    ),
    'female': (
        "tousled shoulder-length hair with a bold colored streak, "
        "wearing a hooded hero outfit with a graphic jacket in vivid clashing colors "
        "and neon accent trim"
    ),
    'neutral': (
        "expressive tousled hair with a neon streak, "
        "wearing a colorful hooded hero outfit with bold graphic accents"
    ),
}

_STYLE_PRESETS = {
    'ghibli': {
        'preamble': _GHIBLI_STYLE_PREAMBLE,
        'exclusions': _GHIBLI_EXCLUSIONS,
        'medical_softening': _GHIBLI_MEDICAL_SOFTENING,
        'archetypes': _GHIBLI_ARCHETYPES,
        'proportions': (
            "with Ghibli child proportions — large round head, high forehead, "
            "soft circular face, round puffy cheeks, stubby limbs, mitten-like hands"
        ),
        'expression': (
            "Warm and brave — large round dark eyes with single white highlight dot top-left, "
            "tiny dot nose, simple small mouth expressing the emotion of this scene. "
            "Round puffy cheeks with subtle warm-pink blush if showing strong positive emotion."
        ),
        'companion_non_medical': (
            "Any companion animals use equally round blobby proportions with large shiny eyes "
            "and flat cel-shaded fur in 2 warm tones."
        ),
        'background': (
            "Painterly Ghibli watercolor background — softer and less detailed than the foreground character. "
            "Lush layered foliage or warm indoor setting with rounded furniture, soft rugs, potted plants. "
            "Signature Ghibli cumulus clouds if sky is visible (big fluffy rounded shapes, soft gray-blue shadow undersides). "
            "Warm golden ambient light from windows or soft lamps."
        ),
        'mood': "Warm, magical, safe, hopeful, and brave — a frame from a hand-animated children's film.",
    },
    'spider-punk': {
        'preamble': _SPIDERVERSE_STYLE_PREAMBLE,
        'exclusions': _SPIDERVERSE_EXCLUSIONS,
        'medical_softening': _SPIDERVERSE_MEDICAL_SOFTENING,
        'archetypes': _SPIDERVERSE_ARCHETYPES,
        # Anti-anime guard lives inside proportions itself so it rides high in the prompt.
        'proportions': (
            "with warm child proportions — large round head, soft rounded face, "
            "big simple eyes (NOT glossy anime eyes, NOT sparkly), stubby limbs, a young kid"
        ),
        'expression': (
            "Brave and expressive comic-hero face conveying this scene's emotion, "
            "with a few small hand-drawn energy marks (motion ticks or tiny stars) near the head."
        ),
        'companion_non_medical': (
            "Companion animals drawn in the same comic style — bold black ink outlines, "
            "cel-shaded saturated tones, halftone shadow dots, neon rim light."
        ),
        # Background deliberately simplified to ONE focal point — previous version
        # produced cluttered rainbow/sparks/city noise that competed with the style.
        'background': (
            "SIMPLE and uncluttered — ONE dominant saturated color field with a subtle "
            "halftone gradient, plus a few clean hand-drawn speed lines pointing to the hero. "
            "Avoid competing elements; the character is the single clear focal point. "
            "Background stays flatter and more abstract than the sharply-inked foreground."
        ),
        'mood': (
            "Electric, heroic, joyful, empowering — a vibrant Spider-Verse film frame, safe for a child."
        ),
    },
}

_DEFAULT_STYLE = 'ghibli'


# ── Image prompt builder ─────────────────────────────────────────────

def build_image_prompt(base_prompt: str, child_name: str, age: int,
                       gender: str, page_number: int, total_pages: int,
                       illustration_style: str = '',
                       character_description: str = '') -> str:
    """Build a styled image generation prompt using the Section 7
    structured format. Visual style is selected via ``illustration_style``
    (currently ``ghibli`` or ``spider-punk``)."""

    # Pick visual style preset (defaults to Ghibli)
    style_key = (illustration_style or _DEFAULT_STYLE).strip().lower()
    preset = _STYLE_PRESETS.get(style_key, _STYLE_PRESETS[_DEFAULT_STYLE])

    # CHARACTER — map gender to the preset's archetype
    gender_label = 'boy' if gender == 'male' else 'girl' if gender == 'female' else 'child'
    archetype_key = gender if gender in ('male', 'female') else 'neutral'
    archetype = preset['archetypes'].get(archetype_key, preset['archetypes']['neutral'])

    char_detail = (
        f"{age}-year-old {gender_label} {preset['proportions']}. {archetype}."
    )
    if character_description:
        char_detail += f" Additional appearance: {character_description}."

    # Check if scene contains medical context to apply softening rules
    medical_context = any(
        kw in base_prompt.lower() for kw in (
            'hospital', 'doctor', 'nurse', 'cast', 'bandage', 'medicine',
            'treatment', 'clinic', 'medical', 'iv', 'drip', 'wheelchair',
            'stethoscope', 'thermometer', 'x-ray', 'injection',
        )
    )
    accessories_block = preset['medical_softening'] if medical_context else preset['companion_non_medical']

    # Structured prompt following Section 7 output format
    prompt = (
        f"[STYLE]: {preset['preamble']}\n"
        f"[CHARACTER]: {char_detail} "
        f"Same character appearance maintained consistently across all {total_pages} pages of this story.\n"
        f"[EXPRESSION]: {preset['expression']}\n"
        f"[POSE]: {base_prompt}\n"
        f"[ACCESSORIES]: {accessories_block}\n"
        f"[BACKGROUND]: {preset['background']}\n"
        f"[COMPOSITION]: Story page {page_number} of {total_pages}. "
        f"{'Dynamic comic-poster framing — gentle dutch tilt or low hero angle, character slightly off-center, strong frozen motion, GENEROUS NEGATIVE SPACE (no background clutter). ' if style_key == 'spider-punk' else 'Eye-level or slightly below camera angle for warmth. Generous breathing room around character, natural slightly offset placement (not centered). '}"
        f"3:2 landscape aspect ratio, high resolution storybook page.\n"
        f"[MOOD]: {preset['mood']}\n"
        f"[EXCLUSIONS]: {preset['exclusions']}"
    )

    logger.debug(f'Built {style_key} image prompt for page {page_number}/{total_pages}')
    return prompt


# ── Prompt for translation ───────────────────────────────────────────

def build_translation_prompt(text: str, target_lang: str) -> str:
    """Build a prompt for translating story text while preserving tone."""
    return f"""You are a professional children's book translator with expertise in {target_lang}.

Translate the following children's story text into {target_lang}.

Translation rules:
- Preserve the warm, encouraging, and magical tone exactly.
- Keep all character names unchanged.
- Adapt idioms and expressions so they feel natural in {target_lang} - never translate them literally.
- Match the rhythm and energy of the original (short bouncy sentences stay short and bouncy).
- Ensure the result reads like it was originally written in {target_lang}, not translated.
- Return ONLY the translated text - no explanations, no notes.

Text to translate:
{text}
"""


# ── Prompt for personalization extraction ────────────────────────────

def build_preference_extraction_prompt(story_json: str, feedback: dict) -> str:
    """Build a prompt to extract preferences from a completed story session."""
    return f"""Analyze this children's story and reading session feedback to extract the child's preferences.

Story data: {story_json}
Feedback: {json.dumps(feedback)}

Return JSON with:
{{
  "themes": ["theme1", "theme2"],
  "character_types": ["type1"],
  "settings": ["setting1"],
  "story_elements": ["element1"]
}}
"""
